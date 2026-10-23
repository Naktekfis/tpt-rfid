/*
 * /admin/monitor: open alarms (acknowledge), unverified returns (verify),
 * tools and loans (search, filters, warning email), students (face data:
 * record again, delete). Alarms and returns poll /api/kiosk/state every
 * 3 s; tools and students reload every 15 s and after each action.
 */
(function () {
    'use strict';

    const UI = window.UI;
    const B = window.Board;
    const h = UI.h;
    const CFG = window.ADMIN_MONITOR_CONFIG || {};
    const STATE_MS = 3000;
    const LIST_MS = 15000;
    const DAY = 24 * 3600 * 1000;
    const CLOCK = new Intl.DateTimeFormat('id-ID', {
        timeZone: 'Asia/Jakarta', hour: '2-digit', minute: '2-digit', hour12: false,
    });

    const $ = function (id) { return document.getElementById(id); };

    let tools = [];
    let students = [];
    let lastStateKey = '';

    // ---------- Helpers ----------

    function emptyRow(body, cols, text) {
        body.appendChild(h('tr', null, h('td', { class: 'empty', colspan: String(cols), text: text })));
    }

    // WIB wall clock as a UTC timestamp, so it compares with nowWib().
    function wibMs(value) {
        const t = UI.parseWib(value);
        return t ? Date.UTC(t.y, t.mo - 1, t.d, +t.h, +t.mi) : null;
    }

    function nowWib() {
        return Date.now() + 7 * 3600 * 1000;
    }

    function confirmDialog(title, text, okLabel, danger) {
        const dlg = $('confirm');
        $('confirm-title').textContent = title;
        $('confirm-text').textContent = text;
        const ok = $('confirm-ok');
        ok.textContent = okLabel;
        ok.className = 'btn ' + (danger ? 'btn--danger' : 'btn--primary');
        return new Promise(function (resolve) {
            dlg.addEventListener('close', function onClose() {
                dlg.removeEventListener('close', onClose);
                resolve(dlg.returnValue === 'ok');
            });
            dlg.returnValue = '';
            dlg.showModal();
            ok.focus();
        });
    }

    async function act(button, url, body, okText) {
        button.disabled = true;
        try {
            const res = await UI.postJSON(url, body);
            if (res.success) {
                UI.toast(okText, 'ok');
                return true;
            }
            UI.toast(res.error || 'Permintaan gagal', 'danger');
        } catch (e) {
            UI.toast('Tidak dapat menghubungi server.', 'danger');
        } finally {
            button.disabled = false;
        }
        return false;
    }

    function personCell(name, nim, photo) {
        const img = photo
            ? h('img', { src: photo, alt: '', loading: 'lazy' })
            : h('span', { class: 'person-cell__blank', 'aria-hidden': 'true' });
        if (photo) img.onerror = function () { img.onerror = null; img.src = CFG.placeholderPhoto; };
        return h('div', { class: 'person-cell' }, img,
            h('div', null, h('span', { text: name || '-' }), nim ? h('span', { class: 'sub', text: nim }) : null));
    }

    // ---------- Alarms + unverified returns ----------

    function renderAlarms(alarms) {
        const body = $('alarms-body');
        body.textContent = '';
        $('alarms-count').textContent = alarms.length ? alarms.length + ' alat' : '';
        $('alarms-head').classList.toggle('section-head--danger', alarms.length > 0);
        if (!alarms.length) {
            emptyRow(body, 3, 'Tidak ada alarm terbuka.');
            return;
        }
        alarms.forEach(function (a) {
            const btn = h('button', { type: 'button', class: 'btn btn--danger btn--sm', text: 'Matikan alarm' });
            btn.addEventListener('click', async function () {
                if (await act(btn, '/api/alarms/' + a.alarm_id + '/ack', undefined, 'Alarm ' + (a.tool_name || '') + ' dimatikan.')) refreshState();
            });
            body.appendChild(h('tr', null,
                h('td', null, h('strong', { text: a.tool_name || 'Alat #' + a.tool_id })),
                h('td', { class: 'num', text: UI.formatWibDate(a.started_at) }),
                h('td', { class: 'actions' }, btn)));
        });
    }

    function renderUnverified(rows) {
        const body = $('unverified-body');
        body.textContent = '';
        $('unverified-count').textContent = rows.length ? rows.length + ' alat' : '';
        if (!rows.length) {
            emptyRow(body, 4, 'Semua pengembalian sudah diverifikasi.');
            return;
        }
        rows.forEach(function (r) {
            const btn = h('button', { type: 'button', class: 'btn btn--secondary btn--sm', text: 'Verifikasi' });
            btn.addEventListener('click', async function () {
                if (await act(btn, '/api/admin/transactions/' + r.transaction_id + '/verify_return', undefined,
                    r.tool_name + ' diverifikasi.')) refreshState();
            });
            body.appendChild(h('tr', null,
                h('td', null, h('strong', { text: r.tool_name })),
                h('td', { text: r.borrower_name || '-' }),
                h('td', { class: 'num', text: UI.formatWibDate(r.return_time) }),
                h('td', { class: 'actions' }, btn)));
        });
    }

    async function refreshState() {
        try {
            const s = await UI.fetchJSON('/api/kiosk/state');
            if (!s.success) return;
            const key = JSON.stringify([s.alarms, s.unverified_returns]);
            if (key !== lastStateKey) {
                lastStateKey = key;
                renderAlarms(s.alarms || []);
                renderUnverified(s.unverified_returns || []);
            }
        } catch (e) { /* next poll */ }
    }

    // ---------- Tools and loans ----------

    function toolStatus(t) {
        const kind = B.markOf(t);
        const label = {
            present: ['Di rak', ''],
            borrowed: ['Dipinjam', ''],
            overdue: ['Terlambat', 'status--warn'],
            missing: ['Hilang', 'status--danger'],
            unknown: ['Belum terbaca', 'status--muted'],
        }[kind];
        return h('span', { class: 'legend__item' },
            h('span', { class: 'unit-mark unit-mark--' + kind, 'aria-hidden': 'true' }),
            h('span', { class: 'status ' + label[1], text: label[0] }));
    }

    function matchesDate(t, range) {
        if (!range) return true;
        const ms = wibMs(t.borrow_time_wib);
        if (ms === null) return false;
        const today = Math.floor(nowWib() / DAY);
        const day = Math.floor(ms / DAY);
        if (range === 'yesterday') return day === today - 1;
        return today - day < +range;
    }

    function renderTools() {
        const q = $('loan-search').value.trim().toLowerCase();
        const status = $('loan-status').value;
        const range = $('loan-date').value;
        const rows = tools.filter(function (t) {
            if (status === 'borrowed' && t.status !== 'borrowed') return false;
            if (status === 'overdue' && !t.is_overdue) return false;
            if (range && !matchesDate(t, range)) return false;
            if (!q) return true;
            return [t.name, t.borrower_name, t.borrower_nim].some(function (v) {
                return v && String(v).toLowerCase().indexOf(q) >= 0;
            });
        });
        const borrowed = tools.filter(function (t) { return t.status === 'borrowed'; }).length;
        const overdue = tools.filter(function (t) { return t.is_overdue; }).length;
        $('loans-count').textContent = borrowed + ' dipinjam' + (overdue ? ' · ' + overdue + ' terlambat' : '') +
            ' · ' + tools.length + ' alat';
        const body = $('loans-body');
        body.textContent = '';
        if (!rows.length) {
            emptyRow(body, 6, tools.length ? 'Tidak ada alat yang cocok dengan filter.' : 'Belum ada alat terdaftar.');
            return;
        }
        rows.forEach(function (t) {
            const borrowed = t.status === 'borrowed';
            let action = null;
            if (borrowed && t.borrower_email) {
                action = h('button', { type: 'button', class: 'linkbtn', text: 'Kirim pengingat' });
                action.addEventListener('click', function () { sendWarning(t, action); });
            }
            body.appendChild(h('tr', null,
                h('td', null, h('strong', { text: t.name })),
                h('td', null, borrowed ? personCell(t.borrower_name, t.borrower_nim, t.borrower_photo_url) : h('span', { class: 'muted', text: '-' })),
                h('td', { class: 'num', text: borrowed ? UI.formatWibDate(t.borrow_time_wib, true) : '' }),
                h('td', { class: 'num' + (t.is_overdue ? ' status status--warn' : ''), text: borrowed ? UI.formatWibDate(t.due_at, true) : '' }),
                h('td', null, toolStatus(t)),
                h('td', { class: 'actions' }, action)));
        });
    }

    async function sendWarning(t, button) {
        const ok = await confirmDialog('Kirim pengingat?',
            'Email pengingat pengembalian ' + t.name + ' dikirim ke ' + t.borrower_name + ' (' + t.borrower_email + ').',
            'Kirim email', false);
        if (!ok) return;
        const original = button.textContent;
        button.textContent = 'Mengirim…';
        await act(button, '/api/admin/send_warning_email', {
            student_name: t.borrower_name,
            student_email: t.borrower_email,
            tool_name: t.name,
            borrow_date: t.borrow_time_wib || '',
        }, 'Email pengingat terkirim ke ' + t.borrower_name + '.');
        button.textContent = original;
    }

    // ---------- Students ----------

    function renderStudents() {
        const q = $('student-search').value.trim().toLowerCase();
        const rows = students.filter(function (s) {
            if (!q) return true;
            return [s.name, s.nim, s.email].some(function (v) { return v && v.toLowerCase().indexOf(q) >= 0; });
        });
        const withFace = students.filter(function (s) { return s.has_face; }).length;
        $('students-count').textContent = students.length + ' mahasiswa · ' + withFace + ' dengan data wajah';
        const body = $('students-body');
        body.textContent = '';
        if (!rows.length) {
            emptyRow(body, 5, students.length ? 'Tidak ada mahasiswa yang cocok.' : 'Belum ada mahasiswa terdaftar.');
            return;
        }
        rows.forEach(function (s) {
            const record = h('a', {
                href: CFG.registerUrl + '?student_id=' + encodeURIComponent(s.student_id),
                text: s.has_face ? 'Rekam ulang wajah' : 'Rekam wajah',
            });
            let del = null;
            if (s.has_face) {
                del = h('button', { type: 'button', class: 'linkbtn linkbtn--danger', text: 'Hapus data wajah' });
                del.addEventListener('click', function () { deleteFace(s, del); });
            }
            body.appendChild(h('tr', null,
                h('td', null, personCell(s.name, s.nim, s.photo_url)),
                h('td', null, h('span', { text: s.email }), h('span', { class: 'sub num', text: s.phone })),
                h('td', null, s.has_face
                    ? h('span', { class: 'status', text: 'Ada' })
                    : h('span', { class: 'status status--muted', text: 'Belum ada' })),
                h('td', { class: 'num', text: String(s.open_loans) }),
                h('td', { class: 'actions' }, record, del)));
        });
    }

    async function deleteFace(s, button) {
        const ok = await confirmDialog('Hapus data wajah?',
            'Data pengenalan wajah dan foto profil ' + s.name + ' (' + s.nim + ') akan dihapus. ' +
            'Mahasiswa ini perlu merekam wajah lagi sebelum dapat meminjam alat.',
            'Hapus data wajah', true);
        if (!ok) return;
        if (await act(button, '/api/admin/students/' + s.student_id + '/face/delete', undefined,
            'Data wajah ' + s.name + ' dihapus.')) loadLists();
    }

    // ---------- Load ----------

    async function loadLists() {
        try {
            const res = await Promise.all([
                UI.fetchJSON('/api/admin/tools_status'),
                UI.fetchJSON('/api/admin/students'),
            ]);
            if (res[0].success) {
                tools = res[0].tools || [];
                renderTools();
            } else if (res[0].error === 'Unauthorized') {
                window.location.href = '/admin/login';
                return;
            }
            if (res[1].success) {
                students = res[1].students || [];
                renderStudents();
            }
            $('updated').textContent = 'Diperbarui ' + CLOCK.format(new Date()).replace(':', '.');
        } catch (e) {
            UI.toast('Data tidak dapat dimuat. Periksa koneksi.', 'danger');
        }
    }

    $('loan-search').addEventListener('input', renderTools);
    $('loan-status').addEventListener('change', renderTools);
    $('loan-date').addEventListener('change', renderTools);
    $('student-search').addEventListener('input', renderStudents);

    refreshState();
    loadLists();
    setInterval(refreshState, STATE_MS);
    setInterval(loadLists, LIST_MS);
})();
