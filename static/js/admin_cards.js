/* Admin: let a card past the KTM chip check. The server reads the card (any
 * chip) and keeps only digests; the browser never sees the UID. */
(function () {
    'use strict';
    const UI = window.UI;
    const h = UI.h;
    const $ = function (id) { return document.getElementById(id); };
    const KINDS = { ktm: 'KTM ditolak, tetap KTM', other: 'Kartu NFC lain, satu NIM' };
    let token = null;
    let ready = false;
    let generation = 0;
    let timer = null;
    let expiresAt = 0;

    function kind() { return document.querySelector('input[name="kind"]:checked').value; }
    function status(text) { $('card-status').textContent = text; }
    function setReady(value) { ready = value; $('card-save').disabled = !value; }

    function reset(message) {
        generation += 1;
        clearTimeout(timer);
        token = null;
        setReady(false);
        status(message);
    }

    async function poll(current) {
        if (current !== generation) return;
        if (Date.now() >= expiresAt) { reset('Waktu pembacaan habis. Tekan Baca kartu lagi.'); return; }
        try {
            const res = await UI.fetchJSON('/api/nfc/registration');
            if (current !== generation) return;
            if (!res.success) { reset(res.error || 'Pembacaan berakhir. Ulangi.'); return; }
            setReady(!!res.ready);
            status(res.ready ? 'Kartu terbaca. Tekan Simpan.'
                : res.connected ? 'Tempelkan kartu ke pembaca.' : 'Pembaca belum tersambung.');
            if (res.ready) return;
        } catch (e) {
            status('Koneksi terputus. Mencoba lagi…');
        }
        timer = setTimeout(function () { poll(current); }, 750);
    }

    async function read() {
        reset('Menyiapkan pembaca…');
        const current = generation;
        $('card-error').textContent = '';
        const res = await UI.postJSON('/api/admin/cards/start', {});
        if (current !== generation) return;
        if (!res.success) { reset(res.error || 'Pembaca belum siap.'); return; }
        token = res.token;
        expiresAt = Date.now() + 120000;
        status('Tempelkan kartu ke pembaca.');
        poll(current);
    }

    async function save(ev) {
        ev.preventDefault();
        if (!ready || !token) return;
        $('card-error').textContent = '';
        $('card-save').disabled = true;
        const res = await UI.postJSON('/api/admin/cards', { nfc_token: token, kind: kind(), nim: $('card-nim').value.trim() });
        if (!res.success) {
            $('card-error').textContent = res.error || 'Gagal menyimpan.';
            $('card-save').disabled = false;
            return;
        }
        reset('Tersimpan. Angkat kartu dari pembaca.');
        $('card-nim').value = '';
        UI.toast('Kartu disimpan.', 'ok');
        load();
    }

    async function remove(row, button) {
        button.disabled = true;
        const res = await UI.postJSON('/api/admin/cards/' + row.id + '/delete', {});
        UI.toast(res.success ? 'Kartu dihapus dari daftar.' : res.error || 'Gagal menghapus.', res.success ? 'ok' : 'danger');
        if (res.success) load(); else button.disabled = false;
    }

    async function load() {
        const res = await UI.fetchJSON('/api/admin/cards');
        const warn = $('cards-warn');
        warn.hidden = !res.success || res.can_hash;
        warn.textContent = 'NFC_POLICY_PEPPER belum diatur di .env, kartu belum bisa disimpan. Jalankan scripts/set_special_card.py.';
        const body = $('cards-body');
        body.textContent = '';
        const cards = res.cards || [];
        $('cards-count').textContent = cards.length + ' kartu';
        if (!cards.length) body.appendChild(h('tr', null, h('td', { class: 'empty', colspan: '3', text: 'Belum ada.' })));
        cards.forEach(function (c) {
            const button = h('button', { type: 'button', class: 'btn btn--secondary btn--sm', text: 'Hapus' });
            button.addEventListener('click', function () { remove(c, button); });
            body.appendChild(h('tr', null, h('td', { text: KINDS[c.kind] || c.kind }),
                h('td', { class: 'num', text: UI.formatWibDate(c.created_at) }), h('td', null, button)));
        });
    }

    document.querySelectorAll('input[name="kind"]').forEach(function (el) {
        el.addEventListener('change', function () { $('nim-field').hidden = kind() !== 'other'; });
    });
    $('card-read').addEventListener('click', read);
    $('card-form').addEventListener('submit', save);
    window.addEventListener('pagehide', function () { generation += 1; clearTimeout(timer); });
    load();
})();
