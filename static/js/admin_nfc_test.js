/* Web NFC check (/admin/nfc-test): lists what this phone's browser reads from
 * a card. Display only: nothing is sent to the server or stored. */
(function () {
    'use strict';
    const $ = function (id) { return document.getElementById(id); };
    let controller = null;
    let empty = true;

    function log(text) {
        if (empty) { $('nfc-log').textContent = ''; empty = false; }
        const tr = document.createElement('tr');
        const time = document.createElement('td');
        time.textContent = new Date().toLocaleTimeString('id-ID');
        const what = document.createElement('td');
        what.style.whiteSpace = 'pre-wrap';
        what.textContent = text;
        tr.append(time, what);
        $('nfc-log').prepend(tr);
    }
    function scanning(on, text) {
        $('nfc-scan').hidden = on;
        $('nfc-stop').hidden = !on;
        $('nfc-state').textContent = text;
    }

    function describe(record) {
        let line = 'recordType: ' + record.recordType + (record.mediaType ? ', mediaType: ' + record.mediaType : '');
        if (record.data && (record.recordType === 'text' || record.recordType === 'url')) {
            try {
                line += '\n  teks: ' + new TextDecoder(record.encoding || 'utf-8').decode(record.data);
            } catch (e) { /* not decodable as text: type only */ }
        }
        return line;
    }

    async function start() {
        controller = new AbortController();
        const reader = new NDEFReader();
        reader.onreading = function (ev) {
            const records = ev.message && ev.message.records ? Array.from(ev.message.records) : [];
            log('Kartu terbaca. serialNumber: ' + (ev.serialNumber || '(kosong)') +
                (records.length ? '\n' + records.map(describe).join('\n') : '\n(tanpa record NDEF)'));
        };
        reader.onreadingerror = function () {
            log('Kartu terdeteksi tetapi tidak bisa dibaca (bukan NDEF)');
        };
        scanning(true, 'Menyiapkan NFC…');
        try {
            await reader.scan({ signal: controller.signal });
            scanning(true, 'Tempelkan kartu ke bagian belakang HP.');
        } catch (e) {
            log('Gagal mulai: ' + e.name + ': ' + e.message);
            scanning(false, 'NFC tidak berjalan.');
        }
    }

    if (!('NDEFReader' in window)) {
        $('nfc-unsupported').hidden = false;
        return;
    }
    $('nfc-scan').hidden = false;
    $('nfc-scan').addEventListener('click', start);  // scan() needs a user gesture
    $('nfc-stop').addEventListener('click', function () {
        if (controller) controller.abort();
        controller = null;
        scanning(false, 'Berhenti.');
        log('Pembacaan dihentikan.');
    });
})();
