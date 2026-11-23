/* Admin registration page: the list of cards let past the KTM chip check.
 * New exceptions are made with the registration (register.js, Jenis kartu);
 * the server keeps only digests, so the list shows kind and date. */
(function () {
    'use strict';
    const UI = window.UI;
    const h = UI.h;
    const $ = function (id) { return document.getElementById(id); };
    const KINDS = { ktm: 'KTM ditolak, tetap KTM', other: 'Kartu NFC lain, satu NIM' };

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
        warn.textContent = 'NFC_POLICY_PEPPER belum diatur di .env, kartu pengecualian belum bisa disimpan. Jalankan scripts/set_special_card.py.';
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

    window.AdminCards = { load: load };  // register.js reloads after saving an exception
    load();
})();
