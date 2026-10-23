// Synthetic browser contracts; no app startup, hardware, network or dependencies.
// Run: node --test tests/js/hmi_polling.test.js
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');
const sourceRoot = process.env.HMI_JS_ROOT || path.join(__dirname, '../../static/js');
const source = name => fs.readFileSync(path.join(sourceRoot, name), 'utf8');
const flush = () => new Promise(resolve => setImmediate(resolve));
const never = () => new Promise(() => {});

function sharedUI(fetch) {
    const timers = new Map();
    let nextTimer = 0;
    const context = {
        window: {}, fetch, AbortController, Intl, Date,
        document: { addEventListener() {} },
        setTimeout(fn, ms) { timers.set(++nextTimer, { fn, ms }); return nextTimer; },
        clearTimeout(id) { timers.delete(id); },
    };
    vm.runInNewContext(source('ui.js'), context);
    return { UI: context.window.UI, timers };
}

test('GET deadline covers both stalled headers and stalled JSON; next poll can succeed', async () => {
    for (const stallBody of [false, true]) {
        let requestSignal;
        let requests = 0;
        const { UI, timers } = sharedUI((url, options) => {
            requestSignal = options.signal;
            if (++requests === 2) return Promise.resolve({ json: async () => ({ success: true }) });
            return stallBody ? Promise.resolve({ json: never }) : never();
        });
        const pending = UI.fetchJSON('/synthetic');
        const rejected = assert.rejects(pending, { name: 'TimeoutError' });
        await flush();
        assert.equal([...timers.values()][0].ms, 5000);
        [...timers.values()][0].fn();
        await rejected;
        assert.equal(requestSignal.aborted, true);
        assert.equal(timers.size, 0);
        assert.equal((await UI.fetchJSON('/synthetic')).success, true);
        assert.equal(timers.size, 0);
    }
});

test('GET preserves caller cancellation, including an already cancelled signal', async () => {
    for (const alreadyAborted of [false, true]) {
        let signal;
        const { UI, timers } = sharedUI((url, options) => { signal = options.signal; return never(); });
        const caller = new AbortController();
        if (alreadyAborted) caller.abort();
        const pending = UI.fetchJSON('/synthetic', { signal: caller.signal });
        const rejected = assert.rejects(pending, { name: 'AbortError' });
        caller.abort();
        await rejected;
        assert.equal(signal.aborted, true);
        assert.equal(timers.size, 0);
    }
});

test('POST has no automatic timeout/retry and retains its supplied signal', async () => {
    let requests = 0;
    let received;
    let finish;
    const caller = new AbortController();
    const { UI, timers } = sharedUI((url, options) => {
        requests++;
        received = options;
        return new Promise(resolve => { finish = resolve; });
    });
    const pending = UI.fetchJSON('/synthetic', { method: 'POST', signal: caller.signal });
    assert.equal(timers.size, 0);
    assert.equal(received.signal, caller.signal);
    finish({ json: async () => ({ success: true }) });
    assert.equal((await pending).success, true);
    assert.equal(requests, 1);
});

function adminHarness() {
    const nodes = new Map();
    let creates = 0;
    class Element {
        constructor() { this.children = []; this.listeners = {}; this.value = ''; this.classList = { toggle() {} }; }
        set textContent(value) { this.text = value; this.children = []; }
        get textContent() { return this.text || ''; }
        appendChild(child) { this.children.push(child); return child; }
        addEventListener(event, fn) { this.listeners[event] = fn; }
        setAttribute() {}
        querySelector() { return new Element(); }
    }
    const node = id => {
        if (!nodes.has(id)) nodes.set(id, new Element());
        return nodes.get(id);
    };
    const h = (tag, attrs, ...children) => {
        creates++;
        const el = new Element();
        Object.assign(el, attrs || {});
        children.filter(Boolean).forEach(child => el.appendChild(child));
        return el;
    };
    const tool = { tool_id: 1, type_id: 2, name: 'Synthetic wrench', category: 'tools',
        status: 'borrowed', presence: 'missing', borrower_name: 'Synthetic borrower',
        borrower_email: 'synthetic@example.invalid', borrower_photo_url: '/synthetic.png' };
    let finishTypes;
    const types = new Promise(resolve => { finishTypes = resolve; });
    const intervals = new Map();
    const UI = { h, parseWib() {}, formatWibDate() { return ''; }, loadNotice() {},
        fetchJSON: async url => {
            if (url.endsWith('/tool_types')) return types;
            if (url.endsWith('/tools_status')) return { success: true, tools: [{ ...tool }] };
            return { success: true, alarms: [], unverified_returns: [] };
        },
    };
    vm.runInNewContext(source('admin_monitor.js'), {
        window: { UI, Board: { markOf: t => t.status === 'borrowed' ? 'borrowed' : t.presence } },
        document: { getElementById: node }, Intl, Date,
        setInterval(fn, ms) { intervals.set(ms, fn); },
    });
    return { node, tool, intervals, finishTypes, creates: () => creates };
}

test('live status renders independently of stalled type metadata and avoids unchanged DOM churn', async () => {
    const app = adminHarness();
    await flush();
    assert.equal(app.node('loans-body').children.length, 1);
    const originalRow = app.node('loans-body').children[0];
    const originalCreates = app.creates();
    app.tool.last_seen_at = '2030-01-01T00:00:00';
    app.tool.updated_at = '2030-01-01T00:00:01';
    await app.intervals.get(1000)();
    assert.equal(app.creates(), originalCreates);
    assert.equal(app.node('loans-body').children[0], originalRow);
    app.tool.presence = 'present';
    await app.intervals.get(1000)();
    assert.notEqual(app.node('loans-body').children[0], originalRow);
    const changedRow = app.node('loans-body').children[0];
    app.finishTypes({ success: true, tool_types: [{ type_id: 2, name: 'Synthetic type' }] });
    await flush();
    assert.notEqual(app.node('loans-body').children[0], changedRow);
    const typedRow = app.node('loans-body').children[0];
    await app.intervals.get(1000)();
    assert.equal(app.node('loans-body').children[0], typedRow);
});

test('filters rerender and changes to edit/email fields invalidate retained row closures', async () => {
    const app = adminHarness();
    await flush();
    app.node('loan-search').value = 'no-match';
    app.node('loan-search').listeners.input();
    assert.match(app.node('loans-body').children[0].children[0].textContent, /Tidak ada/);
    app.node('loan-search').value = '';
    app.node('loan-search').listeners.input();
    const originalRow = app.node('loans-body').children[0];
    app.tool.borrower_email = 'changed@example.invalid';
    await app.intervals.get(1000)();
    assert.notEqual(app.node('loans-body').children[0], originalRow);
    const updatedRow = app.node('loans-body').children[0];
    app.tool.category = 'changed category';
    await app.intervals.get(1000)();
    assert.notEqual(app.node('loans-body').children[0], updatedRow);
});
