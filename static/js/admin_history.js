/*
 * /admin/history: transactions for a date range (/api/admin/transactions),
 * export as CSV / Excel (/api/admin/export, fetched so errors show as a
 * toast) or by email (/api/admin/send_export_email).
 */
(function () {
    'use strict';

    const UI = window.UI;
    const h = UI.h;
    const $ = function (id) { return document.getElementById(id); };

    let range = '30';
    let loadVersion = 0;
    let loaded = false;

    // YYYY-MM-DD of today minus `days` in WIB.
    function wibDate(daysAgo) {
        const d = new Date(Date.now() + 7 * 3600 * 1000 - (daysAgo || 0) * 24 * 3600 * 1000);
        return d.toISOString().slice(0, 10);
    }

    function setRange(r) {
        range = r;
        $('end-date').value = wibDate(0);
        $('start-date').value = r === 'all' ? '' : wibDate(+r);
        document.querySelectorAll('[data-range]').forEach(function (b) {
            b.setAttribute('aria-pressed', String(b.getAttribute('data-range') === r));
        });
    }

    function query() {
        const q = [];
        if ($('start-date').value) q.push('start_date=' + $('start-date').value);
        if ($('end-date').value) q.push('end_date=' + $('end-date').value);
        return q.join('&');
    }

    function rangeText() {
        const s = $('start-date').value;
        const e = $('end-date').value;
        const fmt = function (v) { return UI.formatWibDate(v + 'T00:00').replace(/, 00\.00$/, ''); };
        if (s && e) return fmt(s) + ' sampai ' + fmt(e);
        if (s) return 'sejak ' + fmt(s);
        if (e) return 'sampai ' + fmt(e);
        return 'semua waktu';
    }

    function statusCell(t) {
        const cell = h('td');
        if (t.status === 'borrowed') {
            cell.appendChild(t.is_overdue
                ? h('span', { class: 'status status--warn', text: 'Terlambat' })
                : h('span', { class: 'status', text: 'Dipinjam' }));
            return cell;
        }
        cell.appendChild(h('span', { class: 'status status--muted', text: 'Dikembalikan' }));
        if (t.returned_by_name && t.returned_by_name !== t.student_name) {
            cell.appendChild(h('span', { class: 'sub', text: 'oleh ' + t.returned_by_name }));
        }
        if (!t.return_verified) {
            cell.appendChild(h('span', { class: 'sub status status--warn', text: 'belum diverifikasi' }));
        }
        return cell;
    }

    function render(rows) {
        const body = $('history-body');
        body.textContent = '';
        $('history-count').textContent = rows.length + ' transaksi';
        if (!rows.length) {
            body.appendChild(h('tr', null, h('td', { class: 'empty', colspan: '6', text: 'Belum ada peminjaman pada periode ini.' })));
            return;
        }
        rows.forEach(function (t) {
            body.appendChild(h('tr', null,
                h('td', { class: 'num', text: UI.formatWibDate(t.borrow_time) }),
                h('td', null, h('span', { text: t.student_name }), h('span', { class: 'sub num', text: t.student_nim || '' })),
                h('td', null, h('strong', { text: t.tool_name })),
                h('td', { class: 'num' + (t.is_overdue ? ' status status--warn' : ''), text: UI.formatWibDate(t.due_at) }),
                h('td', { class: 'num', text: t.return_time ? UI.formatWibDate(t.return_time) : '-' }),
                statusCell(t)));
        });
    }

    async function load() {
        const s = $('start-date').value;
        const e = $('end-date').value;
        if (s && e && s > e) {
            UI.toast('Tanggal mulai harus sebelum tanggal akhir.', 'warn');
            return;
        }
        const version = ++loadVersion;
        $('history-count').textContent = 'Memuat…';
        try {
            const res = await UI.fetchJSON('/api/admin/transactions?' + query());
            if (version !== loadVersion) return;
            if (!res.success) {
                throw new Error('History unavailable');
            }
            UI.loadNotice('history-error', '');
            loaded = true;
            render(res.data || []);
        } catch (err) {
            if (version !== loadVersion) return;
            $('history-count').textContent = 'Belum diperbarui';
            UI.loadNotice('history-error', 'Riwayat untuk periode ini belum dapat dimuat. Data terakhir tetap ditampilkan.', load);
            if (!loaded) $('history-body').querySelector('.empty').textContent = 'Data riwayat belum tersedia. Coba muat kembali.';
        }
    }

    async function download(format, button) {
        button.disabled = true;
        const label = button.textContent;
        button.textContent = 'Menyiapkan…';
        try {
            const resp = await fetch('/api/admin/export?format=' + format + (query() ? '&' + query() : ''),
                { credentials: 'same-origin' });
            if (!resp.ok) {
                let msg = 'Ekspor gagal';
                try { msg = (await resp.json()).error || msg; } catch (e) { /* not JSON */ }
                UI.toast(msg, 'danger');
                return;
            }
            const blob = await resp.blob();
            const match = /filename="?([^";]+)"?/.exec(resp.headers.get('Content-Disposition') || '');
            const a = h('a', { href: URL.createObjectURL(blob), download: match ? match[1] : 'rekap_peminjaman.' + format });
            document.body.appendChild(a);
            a.click();
            a.remove();
            setTimeout(function () { URL.revokeObjectURL(a.href); }, 1000);
            UI.toast('Berkas ' + format.toUpperCase() + ' diunduh.', 'ok');
        } catch (e) {
            UI.toast('Tidak dapat menghubungi server.', 'danger');
        } finally {
            button.disabled = false;
            button.textContent = label;
        }
    }

    function openEmail() {
        $('email-range').textContent = 'Laporan Excel peminjaman ' + rangeText() + ' dikirim ke alamat ini.';
        $('email-error').textContent = '';
        $('email-dialog').showModal();
        $('email-input').focus();
    }

    async function sendEmail(ev) {
        ev.preventDefault();
        const input = $('email-input');
        const email = input.value.trim();
        if (!email || !input.checkValidity()) {
            $('email-error').textContent = 'Alamat email belum benar.';
            input.focus();
            return;
        }
        const btn = $('email-send');
        btn.disabled = true;
        btn.textContent = 'Mengirim…';
        try {
            const res = await UI.postJSON('/api/admin/send_export_email', {
                email: email,
                start_date: $('start-date').value || null,
                end_date: $('end-date').value || null,
            });
            if (res.success) {
                $('email-dialog').close();
                UI.toast(res.message || 'Email terkirim.', 'ok');
            } else {
                $('email-error').textContent = res.error || 'Email gagal dikirim.';
            }
        } catch (e) {
            $('email-error').textContent = 'Tidak dapat menghubungi server.';
        } finally {
            btn.disabled = false;
            btn.textContent = 'Kirim';
        }
    }

    document.querySelectorAll('[data-range]').forEach(function (b) {
        b.addEventListener('click', function () {
            setRange(b.getAttribute('data-range'));
            load();
        });
    });
    $('filter-form').addEventListener('submit', function (ev) {
        ev.preventDefault();
        range = '';
        document.querySelectorAll('[data-range]').forEach(function (b) { b.setAttribute('aria-pressed', 'false'); });
        load();
    });
    $('btn-csv').addEventListener('click', function () { download('csv', $('btn-csv')); });
    $('btn-xlsx').addEventListener('click', function () { download('xlsx', $('btn-xlsx')); });
    $('btn-email').addEventListener('click', openEmail);
    $('email-form').addEventListener('submit', sendEmail);
    $('email-cancel').addEventListener('click', function () { $('email-dialog').close(); });

    setRange(range);
    load();
})();
