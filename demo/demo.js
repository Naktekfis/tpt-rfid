/*
 * UI demo without a backend: answers fetch() from the recordings in
 * window.DEMO_DATA (built by scripts/build_demo.py) and adds a panel on the
 * kiosk to step through its states. Writes only pretend to succeed.
 */
(function () {
    'use strict';
    const DATA = window.DEMO_DATA;
    const KEY = 'tpt-demo-kiosk';
    // Real kiosk screens time out after 5 s (utils/kiosk.py); the demo follows.
    const TIMEOUTS = {
        unknown_card: ['idle', 5],
        summary: ['after', 5],
        session: ['summary', DATA.kiosk.session.expires_in],
        borrowed: ['summary', DATA.kiosk.borrowed.expires_in],
    };

    function load() {
        const asked = new URLSearchParams(location.search).get('state');  // shareable: /kiosk?state=alarm
        if (asked && DATA.kiosk[asked]) return { name: asked, at: Date.now() };
        try {
            const v = JSON.parse(localStorage.getItem(KEY));
            if (v && DATA.kiosk[v.name]) return v;
        } catch (e) { /* storage blocked: start idle */ }
        return { name: 'idle', at: Date.now() };
    }
    let current = load();

    function go(name) {
        current = { name: name, at: Date.now() };
        try { localStorage.setItem(KEY, JSON.stringify(current)); } catch (e) { /* per-tab only */ }
        markPanel();
    }

    function kioskState() {
        const elapsed = (Date.now() - current.at) / 1000;
        const next = TIMEOUTS[current.name];
        if (next && elapsed >= next[1]) go(next[0]);
        const s = JSON.parse(JSON.stringify(DATA.kiosk[current.name]));
        const left = function (v) { return Math.max(0, Math.round((v - elapsed) * 10) / 10); };
        if ('expires_in' in s) s.expires_in = left(s.expires_in);
        if ('summary_ends_in' in s) s.summary_ends_in = left(s.summary_ends_in);
        if ('unknown_ends_in' in s) s.unknown_ends_in = left(s.unknown_ends_in);
        return s;
    }

    function post(path) {
        if (path === '/api/kiosk/end') go('summary');
        else if (path === '/api/kiosk/cancel') go('idle');
        else if (/^\/api\/alarms\/\d+\/ack$/.test(path)) go('after');
        return { success: true, message: 'Mode demo: perubahan tidak disimpan.' };
    }

    function reply(body) {
        return Promise.resolve(new Response(JSON.stringify(body), {
            status: 200, headers: { 'Content-Type': 'application/json' },
        }));
    }

    const realFetch = window.fetch.bind(window);
    window.fetch = function (input, init) {
        const url = new URL(typeof input === 'string' ? input : input.url, location.href);
        const method = ((init && init.method) || 'GET').toUpperCase();
        const path = url.pathname;
        if (url.origin !== location.origin || path.startsWith('/static/')) return realFetch(input, init);
        if (method !== 'GET') return reply(post(path));
        if (path === '/api/kiosk/state') return reply(kioskState());
        if (path === '/admin/logout') return reply({ success: true });
        if (DATA.api[path]) return reply(DATA.api[path]);
        return reply({ success: false, error: 'Tidak tersedia di mode demo.' });
    };

    // ---- panel (kiosk + monitor) and badge (other pages) ----

    const STEPS = [
        ['idle', 'Siaga'],
        ['unknown_card', 'Kartu tak dikenal'],
        ['session', 'Tap kartu'],
        ['borrowed', 'Ambil bor'],
        ['summary', 'Selesai'],
        ['alarm', 'Alarm'],
    ];
    let panel = null;

    function markPanel() {
        if (!panel) return;
        panel.querySelectorAll('button').forEach(function (b) {
            b.setAttribute('aria-pressed', String(b.dataset.step === current.name));
        });
    }

    function css() {
        const style = document.createElement('style');
        style.textContent =
            // Admin pages: bottom left; kiosk: top right (its action buttons sit at the bottom).
            '.demo-bar--kiosk{left:auto!important;bottom:auto!important;right:12px;top:12px;justify-content:flex-end}' +
            '.demo-bar{position:fixed;left:12px;bottom:12px;z-index:9999;display:flex;flex-wrap:wrap;gap:6px;align-items:center;' +
            'max-width:calc(100vw - 24px);padding:8px 10px;border-radius:12px;background:rgba(20,24,32,.92);color:#fff;' +
            'font:13px/1.2 system-ui,sans-serif;box-shadow:0 4px 16px rgba(0,0,0,.3)}' +
            // Phone: the admin tab bar (56px) sits at the bottom, so lift the bar above it.
            '@media(max-width:600px){.demo-bar:not(.demo-bar--kiosk){bottom:calc(68px + env(safe-area-inset-bottom,0px))}}' +
            '.demo-bar b{margin-right:4px;letter-spacing:.04em}' +
            '.demo-bar button,.demo-bar a{font:inherit;color:#fff;background:rgba(255,255,255,.12);border:1px solid rgba(255,255,255,.25);' +
            'border-radius:8px;padding:6px 10px;cursor:pointer;text-decoration:none}' +
            '.demo-bar button[aria-pressed="true"]{background:#005aab;border-color:#4d9be6}' +
            '.demo-bar button:focus-visible,.demo-bar a:focus-visible{outline:2px solid #fff;outline-offset:2px}' +
            '.demo-bar--hidden>:not(.demo-toggle){display:none}';
        document.head.appendChild(style);
    }

    function el(tag, attrs, text) {
        const e = document.createElement(tag);
        Object.keys(attrs).forEach(function (k) { e.setAttribute(k, attrs[k]); });
        if (text) e.textContent = text;
        return e;
    }

    document.addEventListener('DOMContentLoaded', function () {
        css();
        const page = location.pathname.replace(/\/$/, '');
        const kiosk = page === '/kiosk' || page === '/monitor';
        panel = el('div', { class: 'demo-bar', role: 'region', 'aria-label': 'Kontrol demo' });
        panel.appendChild(el('b', {}, 'DEMO'));
        if (kiosk) {
            panel.classList.add('demo-bar--kiosk');
            STEPS.forEach(function (s) {
                const b = el('button', { type: 'button', 'data-step': s[0] }, s[1]);
                b.addEventListener('click', function () { go(s[0]); });
                panel.appendChild(b);
            });
            panel.appendChild(el('a', { href: '/admin/login' }, 'Admin →'));
        } else {
            panel.appendChild(el('span', {}, 'Data contoh, perubahan tidak disimpan.'));
            panel.appendChild(el('a', { href: '/kiosk' }, 'Kiosk'));
            if (page === '/admin/login') panel.appendChild(el('span', {}, 'PIN apa saja.'));
        }
        const toggle = el('button', { type: 'button', class: 'demo-toggle', 'aria-label': 'Sembunyikan kontrol demo' }, '×');
        toggle.addEventListener('click', function () {
            const hidden = panel.classList.toggle('demo-bar--hidden');
            toggle.textContent = hidden ? 'DEMO' : '×';
            toggle.setAttribute('aria-label', hidden ? 'Tampilkan kontrol demo' : 'Sembunyikan kontrol demo');
        });
        panel.appendChild(toggle);
        document.body.appendChild(panel);
        markPanel();
    });
})();
