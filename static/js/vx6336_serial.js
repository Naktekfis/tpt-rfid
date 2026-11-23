/*
 * HW-VX6336 UHF reader plugged into this computer, read through Web Serial
 * (Chrome/Edge desktop, HTTPS). Port of the read-only part of utils/vx6336.py:
 * only Inventory 0x01 is ever sent, nothing that changes the reader or a tag.
 * See .claude/knowledge/RFID_VX6336.md (57600 8N1; empty field answers in ~23 ms).
 *
 *   const link = await VX6336Serial.connect({ onEpcs, onState });  // user gesture
 *   link.close();
 *
 * onEpcs(list) gets the EPCs (uppercase hex) read within the last HOLD_MS.
 * onState('connected' | 'lost' | 'closed', message?) reports the port.
 */
(function (root) {
    'use strict';

    const BAUD = 57600;
    const CMD_INVENTORY = 0x01;
    const STATUS_MORE = 0x03;
    // Statuses whose Data carries Num + EPCs (utils/vx6336.INVENTORY_DATA_STATUSES).
    const DATA_STATUSES = [0x00, 0x01, 0x02, 0x03, 0x04];
    const MIN_LEN = 5;  // Len byte of a response with empty Data
    const ROUND_TIMEOUT_MS = 30000;  // longer than a ScanTime-255 round (25.5 s)
    const ROUND_GAP_MS = 100;
    const HOLD_MS = 1500;  // a tag stays listed this long after its last read

    function crc16(bytes) {
        let crc = 0xFFFF;
        for (let i = 0; i < bytes.length; i++) {
            crc ^= bytes[i];
            for (let b = 0; b < 8; b++) crc = (crc & 1) ? (crc >>> 1) ^ 0x8408 : crc >>> 1;
        }
        return crc;
    }

    function inventoryFrame() {
        const body = [0x04, 0x00, CMD_INVENTORY];
        const crc = crc16(body);
        return new Uint8Array(body.concat([crc & 0xFF, crc >>> 8]));
    }

    function hex(bytes) {
        let out = '';
        for (let i = 0; i < bytes.length; i++) out += (bytes[i] < 16 ? '0' : '') + bytes[i].toString(16);
        return out.toUpperCase();
    }

    // Inventory Data: Num, then EPCLen + EPC per tag. Throws on a short payload.
    function parseEpcs(data) {
        if (!data.length) return [];
        const epcs = [];
        let pos = 1;
        for (let n = 0; n < data[0]; n++) {
            if (pos >= data.length) throw new Error('Inventory data ends before Num tags');
            const len = data[pos++];
            if (pos + len > data.length) throw new Error('Inventory data ends inside an EPC');
            epcs.push(hex(data.slice(pos, pos + len)));
            pos += len;
        }
        return epcs;
    }

    // The frame starting at buf[start] if it is complete with a good CRC.
    function frameAt(buf, start) {
        const len = buf[start];
        if (len < MIN_LEN || start + len + 1 > buf.length) return null;
        const frame = buf.slice(start, start + len + 1);
        const got = frame[len - 1] | (frame[len] << 8);
        if (crc16(frame.slice(0, len - 1)) !== got) return null;
        return { addr: frame[1], cmd: frame[2], status: frame[3], data: frame.slice(4, len - 1) };
    }

    // Reassembles response frames from serial chunks, like utils/vx6336.FrameSplitter:
    // a bad Len or CRC drops one byte; a head that claims a frame longer than
    // what has arrived may be garbage, so a complete frame further in wins.
    function FrameSplitter() { this.buf = []; }
    FrameSplitter.prototype.feed = function (chunk) {
        for (let i = 0; i < chunk.length; i++) this.buf.push(chunk[i]);
        const out = [];
        while (this.buf.length) {
            const len = this.buf[0];
            if (len < MIN_LEN) { this.buf.shift(); continue; }
            if (this.buf.length < len + 1) {
                let found = null;
                for (let s = 1; s < this.buf.length && !found; s++) {
                    const f = frameAt(this.buf, s);
                    if (f) { found = f; this.buf.splice(0, s + this.buf[s] + 1); }
                }
                if (!found) break;
                out.push(found);
                continue;
            }
            const f = frameAt(this.buf, 0);
            if (!f) { this.buf.shift(); continue; }
            this.buf.splice(0, len + 1);
            out.push(f);
        }
        return out;
    };

    function supported() {
        return !!(root.navigator && root.navigator.serial);
    }

    async function connect(opts) {
        const onEpcs = opts.onEpcs || function () {};
        const onState = opts.onState || function () {};
        const serial = root.navigator.serial;
        // A port allowed before is reused without asking; otherwise the browser asks.
        const granted = await serial.getPorts();
        const port = granted.length === 1 ? granted[0] : await serial.requestPort();
        await port.open({ baudRate: BAUD, dataBits: 8, stopBits: 1, parity: 'none' });
        const reader = port.readable.getReader();
        const writer = port.writable.getWriter();
        const splitter = new FrameSplitter();
        const frames = [];
        const seen = new Map();  // EPC -> last read time
        let wake = null;
        let closed = false;

        function report() {
            const now = Date.now();
            seen.forEach(function (at, epc) { if (now - at > HOLD_MS) seen.delete(epc); });
            onEpcs(Array.from(seen.keys()).sort());
        }

        function nextFrame(timeoutMs) {
            if (frames.length) return Promise.resolve(frames.shift());
            return new Promise(function (resolve) {
                const timer = setTimeout(function () { wake = null; resolve(null); }, timeoutMs);
                wake = function () { clearTimeout(timer); wake = null; resolve(frames.shift() || null); };
            });
        }

        async function readLoop() {
            try {
                for (;;) {
                    const r = await reader.read();
                    if (r.done) break;
                    splitter.feed(r.value).forEach(function (f) { frames.push(f); });
                    if (wake && frames.length) wake();
                }
            } catch (e) { /* unplugged: the poll loop notices */ }
            if (!closed) lost('Reader di PC ini terputus.');
        }

        async function pollLoop() {
            while (!closed) {
                try {
                    await writer.write(inventoryFrame());
                } catch (e) {
                    lost('Reader di PC ini terputus.');
                    return;
                }
                // One round: frames until a status other than "more follows".
                for (;;) {
                    const f = await nextFrame(ROUND_TIMEOUT_MS);
                    if (f === null) { lost('Reader tidak menjawab.'); return; }
                    if (f.cmd !== CMD_INVENTORY) continue;
                    if (DATA_STATUSES.indexOf(f.status) >= 0) {
                        try {
                            parseEpcs(f.data).forEach(function (epc) { seen.set(epc, Date.now()); });
                        } catch (e) { /* malformed round: skip it */ }
                    }
                    if (f.status !== STATUS_MORE) break;
                }
                report();
                await new Promise(function (r) { setTimeout(r, ROUND_GAP_MS); });
            }
        }

        async function release() {
            closed = true;
            seen.clear();
            onEpcs([]);
            try { await reader.cancel(); } catch (e) { /* already gone */ }
            try { reader.releaseLock(); writer.releaseLock(); } catch (e) { /* already released */ }
            try { await port.close(); } catch (e) { /* unplugged */ }
        }

        function lost(message) {
            if (closed) return;
            release();
            onState('lost', message);
        }

        onState('connected');
        readLoop();
        pollLoop();
        return {
            close: async function () {
                if (closed) return;
                await release();
                onState('closed');
            },
        };
    }

    root.VX6336Serial = {
        supported: supported,
        connect: connect,
        // exposed for tests
        crc16: crc16,
        inventoryFrame: inventoryFrame,
        parseEpcs: parseEpcs,
        FrameSplitter: FrameSplitter,
    };
})(typeof window !== 'undefined' ? window : globalThis);
