/*
 * /admin/monitor: open alarms (acknowledge), unverified returns (verify),
 * tools and loans (search, filters, editing, warning email). Alarms and returns
 * poll alerts every 500 ms, tools every second and types every minute/after edits.
 */
(function () {
    'use strict';

    const UI = window.UI;
    const B = window.Board;
    const h = UI.h;
    const CFG = window.ADMIN_MONITOR_CONFIG || {};
    const STATE_MS = 500;
    const LIST_MS = 1000;
    const TYPES_MS = 60000;
    const DAY = 24 * 3600 * 1000;
    const CLOCK = new Intl.DateTimeFormat('id-ID', {
        timeZone: 'Asia/Jakarta', hour: '2-digit', minute: '2-digit', hour12: false,
    });

    const $ = function (id) { return document.getElementById(id); };

    let tools = [];
    let types = [];
    let editing = null;
    let lastStateKey = '';
    let toolsLoaded = false;
    let listsLoading = false;
    let stateLoading = false;
    let typesLoading = false;
    let lastToolsKey = '';

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
        button.setAttribute('aria-busy', 'true');
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
            button.removeAttribute('aria-busy');
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
        if (stateLoading) return;
        stateLoading = true;
        try {
            const s = await UI.fetchJSON('/api/admin/kiosk/alerts');
            if (!s.success) throw new Error('State unavailable');
            UI.loadNotice('state-error', '');
            const key = JSON.stringify([s.alarms, s.unverified_returns]);
            if (key !== lastStateKey) {
                lastStateKey = key;
                renderAlarms(s.alarms || []);
                renderUnverified(s.unverified_returns || []);
            }
        } catch (e) {
            UI.loadNotice('state-error', 'Alarm dan pengembalian belum dapat diperbarui. Data terakhir tetap ditampilkan; mencoba kembali otomatis.', refreshState);
            if (!lastStateKey) {
                ['alarms-body', 'unverified-body'].forEach(function (id) {
                    $(id).querySelector('.empty').textContent = 'Data belum tersedia. Periksa pesan di atas.';
                });
            }
        } finally { stateLoading = false; }
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
        // Inventory timestamps change every scan, without changing anything shown.
        // Include fields used by button closures as well as visible/filter fields.
        const key = JSON.stringify([q, status, range, range ? Math.floor(nowWib() / DAY) : null,
            tools.map(function (t) {
                return [t.tool_id, t.type_id, t.name, t.category, t.rfid_uid,
                    t.status, t.presence, t.is_overdue, t.borrower_name, t.borrower_nim,
                    t.borrower_email, t.borrower_photo_url, t.borrow_time_wib, t.due_at];
            }), types.map(function (t) { return [t.type_id, t.name]; })]);
        if (key === lastToolsKey) return;
        lastToolsKey = key;
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
            const edit = h('button', { type: 'button', class: 'linkbtn', text: 'Edit alat' });
            edit.addEventListener('click', function () { editTool(t, null); });
            const type = types.find(function (entry) { return String(entry.type_id) === String(t.type_id); });
            let rename = null;
            if (type) {
                rename = h('button', { type: 'button', class: 'linkbtn', text: 'Edit jenis' });
                rename.addEventListener('click', function () { editTool(t, type); });
            }
            body.appendChild(h('tr', null,
                h('td', null, h('strong', { text: t.name }), h('span', { class: 'sub num', text: t.rfid_uid || '' })),
                h('td', null, borrowed ? personCell(t.borrower_name, t.borrower_nim, t.borrower_photo_url) : h('span', { class: 'muted', text: '-' })),
                h('td', { class: 'num', text: borrowed ? UI.formatWibDate(t.borrow_time_wib, true) : '' }),
                h('td', { class: 'num' + (t.is_overdue ? ' status status--warn' : ''), text: borrowed ? UI.formatWibDate(t.due_at, true) : '' }),
                h('td', null, toolStatus(t)),
                h('td', { class: 'actions' }, edit, rename, action)));
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

    // ---------- Tool editing ----------

    function editTool(tool, type) {
        editing = { tool: tool, type: type };
        $('edit-title').textContent = type ? 'Edit jenis alat' : 'Edit alat';
        $('edit-name').value = type ? type.name : tool.name;
        $('edit-category').value = tool.category || '';
        $('edit-category-field').hidden = !!type;
        $('edit-category').required = !type;
        $('edit-hint').textContent = type
            ? 'Nama baru berlaku untuk semua unit dalam jenis ini.'
            : 'EPC, status rak, dan status peminjaman tetap dikelola sistem.';
        $('edit-tool').showModal();
        $('edit-name').focus();
    }

    $('edit-cancel').addEventListener('click', function () { $('edit-tool').close(); });
    $('edit-form').addEventListener('submit', async function (event) {
        event.preventDefault();
        const current = editing;
        const url = current.type
            ? '/api/admin/tool_types/' + current.type.type_id + '/edit'
            : '/api/admin/tool_units/' + current.tool.tool_id + '/edit';
        if (await act($('edit-save'), url, {
            name: $('edit-name').value.trim(), category: $('edit-category').value.trim(),
        }, 'Data alat diperbarui.')) {
            $('edit-tool').close();
            loadLists();
            loadTypes();
            refreshState();
        }
    });

    // ---------- Load ----------

    async function loadTypes() {
        if (typesLoading) return;
        typesLoading = true;
        try {
            const result = await UI.fetchJSON('/api/admin/tool_types');
            if (!result.success) return;
            types = result.tool_types || [];
            if (toolsLoaded) renderTools();
        } catch (e) {
            // Keep the last type metadata; live tool status loads independently.
        } finally { typesLoading = false; }
    }

    async function loadLists() {
        if (listsLoading) return;
        listsLoading = true;
        try {
            const res = await UI.fetchJSON('/api/admin/tools_status');
            if (res.error === 'Unauthorized') {
                window.location.href = '/admin/login';
                return;
            }
            if (!res.success) throw new Error('Lists unavailable');
            UI.loadNotice('tools-error', '');
            toolsLoaded = true;
            tools = res.tools || [];
            renderTools();
            $('updated').textContent = 'Diperbarui ' + CLOCK.format(new Date()).replace(':', '.');
        } catch (e) {
            UI.loadNotice('tools-error', 'Daftar alat belum dapat diperbarui. Data terakhir tetap ditampilkan; mencoba kembali otomatis.', loadLists);
            if (!toolsLoaded) {
                $('loans-body').textContent = '';
                emptyRow($('loans-body'), 6, 'Data alat belum tersedia. Coba muat kembali.');
            }
        } finally { listsLoading = false; }
    }

    $('loan-search').addEventListener('input', renderTools);
    $('loan-status').addEventListener('change', renderTools);
    $('loan-date').addEventListener('change', renderTools);

    refreshState();
    loadLists();
    loadTypes();
    setInterval(refreshState, STATE_MS);
    setInterval(loadLists, LIST_MS);
    setInterval(loadTypes, TYPES_MS);
})();
