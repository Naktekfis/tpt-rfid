// Web Serial VX6336 reader (static/js/vx6336_serial.js) against the protocol
// vectors in .claude/knowledge/RFID_VX6336.md and a fake serial port.
// Run: node --test tests/js/vx6336_serial.test.js
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');

const SRC = fs.readFileSync(path.join(__dirname, '../../static/js/vx6336_serial.js'), 'utf8');

function load(navigator) {
    const context = { window: { navigator }, setTimeout, clearTimeout, Map, Uint8Array, Date, Promise };
    vm.runInNewContext(SRC, context);
    return context.window.VX6336Serial;
}

const S = load({});
const EPC1 = 'E28068940000401A2C141084';
const EPC2 = 'E2000017221101AA01000000';

function withCrc(body) {
    const crc = S.crc16(body);
    return body.concat([crc & 0xFF, crc >>> 8]);
}

function inventoryReply(epcs, status = 0x01) {
    const data = [epcs.length];
    epcs.forEach(e => { data.push(e.length / 2); for (let i = 0; i < e.length; i += 2) data.push(parseInt(e.slice(i, i + 2), 16)); });
    return withCrc([data.length + 5, 0x00, 0x01, status].concat(data));
}

test('inventory frame and CRC match the manual vectors', () => {
    assert.deepEqual(Array.from(S.inventoryFrame()), [0x04, 0x00, 0x01, 0xDB, 0x4B]);
    assert.equal(S.crc16([0x06, 0x00, 0x35, 0x00, 0x01]), 0xA58A);  // beep mode reply 06 00 35 00 01 8A A5
});

test('splitter resyncs past garbage and split chunks, parses EPCs', () => {
    const sp = new S.FrameSplitter();
    const frame = inventoryReply([EPC1, EPC2]);
    assert.equal(sp.feed([0x02, 0xFF].concat(frame.slice(0, 7))).length, 0);
    const out = sp.feed(frame.slice(7));
    assert.equal(out.length, 1);
    assert.deepEqual(Array.from(S.parseEpcs(out[0].data)), [EPC1, EPC2]);
    const bad = frame.slice(); bad[bad.length - 1] ^= 0xFF;
    assert.equal(sp.feed(bad).length, 0);  // bad CRC is never returned
});

test('parseEpcs rejects truncated data', () => {
    assert.throws(() => S.parseEpcs([2, 1, 0xAA]));
    assert.deepEqual(Array.from(S.parseEpcs([])), []);
});

function fakePort(replyFor) {
    const chunks = [];
    let waiting = null;
    let unplugged = false;
    const push = c => { if (waiting) { const w = waiting; waiting = null; w({ value: c, done: false }); } else chunks.push(c); };
    return {
        writes: 0,
        unplug() { unplugged = true; if (waiting) waiting({ value: undefined, done: true }); },
        async open(o) { this.opened = o; },
        async close() { this.closed = true; },
        readable: { getReader: () => ({
            read: () => chunks.length ? Promise.resolve({ value: chunks.shift(), done: false })
                : unplugged ? Promise.resolve({ done: true }) : new Promise(r => { waiting = r; }),
            async cancel() { if (waiting) waiting({ done: true }); },
            releaseLock() {},
        }) },
        get writable() {
            const port = this;
            return { getWriter: () => ({
                async write() { if (unplugged) throw new Error('gone'); port.writes++; setTimeout(() => push(replyFor(port.writes)), 1); },
                releaseLock() {},
            }) };
        },
    };
}

test('connect polls the reader, reports EPCs and notices an unplug', async () => {
    const port = fakePort(n => inventoryReply(n < 3 ? [EPC1] : []));
    const Serial = load({ serial: { getPorts: async () => [port], requestPort: async () => { throw new Error('no prompt expected'); } } });
    const seen = [];
    const states = [];
    await Serial.connect({ onEpcs: l => seen.push(Array.from(l)), onState: (s, m) => states.push([s, m]) });
    assert.equal(port.opened.baudRate, 57600);
    await new Promise(r => setTimeout(r, 350));
    assert.ok(seen.some(l => l.length === 1 && l[0] === EPC1));
    port.unplug();
    await new Promise(r => setTimeout(r, 250));
    assert.equal(states[0][0], 'connected');
    assert.equal(states[states.length - 1][0], 'lost');
    assert.ok(port.closed);
    assert.deepEqual(seen[seen.length - 1], []);
});
