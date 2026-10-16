/*
 * Kiosk screen (design D): polls /api/kiosk/state every second and shows one
 * screen per kiosk state (idle / unknown_face, identifying, session /
 * summary) plus the alarm. The kiosk logic runs server-side; this page only
 * shows it and sends "Selesai" / "Bukan saya" / admin alarm acknowledge.
 */
(function () {
    'use strict';

    const UI = window.UI;
    const h = UI.h;
    const CFG = window.KIOSK_CONFIG || {};

    const POLL_MS = 1000;
    const DEVICE_POLL_MS = 5000;
    const CAMERA_RETRY_MS = 10000;
    const REASON_SHOW_MS = 8000;
    const STATES = ['idle', 'identifying', 'unknown_face', 'session', 'summary'];

    const REASONS = {
        challenge_timeout: 'Verifikasi belum selesai dalam waktu yang tersedia. Lihat ke kamera untuk mencoba lagi.',
        different_face: 'Wajah yang terlihat berganti selama verifikasi. Silakan ulangi dari awal.',
        face_lost: 'Wajah tidak terlihat lagi oleh kamera. Lihat ke kamera untuk mengulang.',
        cancelled: 'Sesi dibatalkan. Tidak ada alat yang tercatat.',
    };

    // Backend direction is in raw-image terms: "left" means the person turns
    // to their own right, which is the screen right in the mirrored preview.
    const TURNS = {
        left: { text: 'Tengok ke kanan', toLeft: false },
        right: { text: 'Tengok ke kiri', toLeft: true },
    };

    // Unit mark kinds, in legend order.
    const MARKS = [
        ['present', 'di rak'],
        ['mine', 'Anda pinjam'],
        ['borrowed', 'dipinjam'],
        ['overdue', 'terlambat'],
        ['missing', 'hilang'],
        ['unknown', 'belum terbaca'],
    ];

    const $ = function (id) { return document.getElementById(id); };

    let lastState = null;
    let lastBoardKey = '';
    let lastListsKey = '';
    let lastUnverifiedKey = '';
    let lastAlarmKey = '';
    let reasonShownAt = 0;
    let alarmIds = [];
    let serverDown = false;
    let devices = null;
    let toolInfo = {};   // tool_id -> {photo, typeName} from the last board

    // ---------- Clock ----------

    const timeFmt = new Intl.DateTimeFormat('id-ID', {
        timeZone: 'Asia/Jakarta', hour: '2-digit', minute: '2-digit', hour12: false,
    });

    function tickClock() {
        const text = timeFmt.format(new Date()).replace(':', '.');
        document.querySelectorAll('[data-clock]').forEach(function (el) {
            if (el.textContent !== text) el.textContent = text;
        });
    }

    // ---------- Banners ----------

    function renderBanners() {
        const box = $('banners');
        box.textContent = '';
        if (serverDown) {
            box.appendChild(h('div', { class: 'bar bar--danger', role: 'alert' },
                'Koneksi ke server terputus. Data di layar mungkin tidak terbaru.'));
            return;
        }
        if (!devices) return;
        const r = devices.reader || {};
        const c = devices.camera || {};
        if (r.mode === 'serial' && !r.connected) {
            box.appendChild(h('div', { class: 'bar bar--warn', role: 'status' },
                'Pembaca RFID tidak terhubung. Peminjaman dan pengembalian belum tercatat sampai pembaca tersambung kembali.'));
        }
        if (c.enabled && !cameraOk(c)) {
            box.appendChild(h('div', { class: 'bar bar--warn', role: 'status' },
                'Kamera tidak mengirim gambar. Pengenalan wajah tidak berjalan.'));
        }
    }

    function cameraOk(c) {
        return !!(c.enabled && c.running && c.opened && c.frame_age !== null && c.frame_age < 3);
    }

    async function pollDevices() {
        try {
            const data = await UI.fetchJSON('/api/devices/status');
            devices = data.success ? data : null;
        } catch (e) {
            devices = null;
        }
        renderBanners();
        setTimeout(pollDevices, DEVICE_POLL_MS);
    }

    // ---------- Camera ----------

    function startCamera() {
        const img = $('camera-img');
        img.onload = function () {
            $('camera-placeholder').hidden = true;
            img.hidden = false;
        };
        img.onerror = function () {
            img.hidden = true;
            $('camera-placeholder').hidden = false;
            setTimeout(function () {
                img.src = CFG.cameraStream + '?t=' + Date.now();
            }, CAMERA_RETRY_MS);
        };
        img.src = CFG.cameraStream;
    }

    // mode: 'guide' (dashed oval), 'ok' (green oval), 'turn' (arrow + strip)
    function placeCamera(slot, mode, opts) {
        const cam = $('camera');
        if (!slot) {
            cam.hidden = true;
            return;
        }
        if (cam.parentNode !== slot) slot.appendChild(cam);
        const o = opts || {};
        cam.className = 'camera camera--' + (mode === 'turn' ? 'turn' : 'guide') +
            (mode === 'ok' ? ' camera--ok' : '') +
            (o.small ? ' camera--small' : '') +
            (o.toLeft ? ' camera--to-left' : '');
        cam.hidden = false;
    }

    // ---------- Tool photos and unit marks ----------

    function initials(name) {
        const words = String(name || '').trim().split(/\s+/).filter(Boolean);
        if (!words.length) return '';
        if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
        return (words[0][0] + words[1][0]).toUpperCase();
    }

    function toolPhoto(url, name, size) {
        const tile = h('div', { class: 'tool-photo tool-photo--' + size });
        const fallback = function () {
            tile.textContent = '';
            tile.appendChild(h('span', { class: 'tool-photo__initials', 'aria-hidden': 'true', text: initials(name) }));
        };
        if (url) {
            const img = h('img', { src: url, alt: 'Foto ' + name, loading: 'lazy' });
            img.onerror = fallback;
            tile.appendChild(img);
        } else {
            fallback();
        }
        return tile;
    }

    function markOf(u, mine) {
        if (u.status === 'borrowed') {
            if (u.is_overdue) return 'overdue';
            return mine[String(u.tool_id)] ? 'mine' : 'borrowed';
        }
        if (u.status === 'available') {
            if (u.presence === 'present') return 'present';
            if (u.presence === 'missing') return 'missing';
        }
        return 'unknown';
    }

    function markTitle(u, kind) {
        const label = MARKS.filter(function (m) { return m[0] === kind; })[0][1];
        let text = u.name + ': ' + label;
        if (u.borrower_name && kind !== 'mine') text += ' (' + u.borrower_name + ')';
        if (u.due_at) text += ', batas ' + UI.formatWibDate(u.due_at, true);
        return text;
    }

    function summarize(board, mine) {
        const used = {};
        let present = 0;
        let total = 0;
        const groups = board.map(function (g) {
            const marks = g.units.map(function (u) {
                const kind = markOf(u, mine);
                used[kind] = true;
                return { kind: kind, title: markTitle(u, kind) };
            });
            const n = function (kind) { return marks.filter(function (m) { return m.kind === kind; }).length; };
            present += n('present');
            total += marks.length;
            return {
                name: g.type_name,
                photo: g.photo_url,
                marks: marks,
                present: n('present'),
                overdue: n('overdue'),
                missing: n('missing'),
            };
        });
        return { groups: groups, used: used, present: present, total: total };
    }

    function unitsEl(marks, small) {
        const row = h('div', { class: 'units' + (small ? ' units--sm' : '') });
        marks.forEach(function (m) {
            row.appendChild(h('span', { class: 'unit-mark unit-mark--' + m.kind, title: m.title }));
        });
        return row;
    }

    function countEl(g) {
        let text = g.present + ' dari ' + g.marks.length;
        let kind = '';
        if (g.overdue) {
            text += ' · ' + g.overdue + ' terlambat';
            kind = ' count--warn';
        }
        if (g.missing) {
            text += ' · ' + g.missing + ' hilang';
            kind = ' count--danger';
        }
        return h('div', { class: 'count' + kind, text: text });
    }

    function legendInto(box, used) {
        box.textContent = '';
        MARKS.forEach(function (m) {
            if (m[0] !== 'present' && !used[m[0]]) return;
            box.appendChild(h('span', { class: 'legend__item' },
                h('span', { class: 'unit-mark unit-mark--' + m[0], 'aria-hidden': 'true' }), m[1]));
        });
    }

    // ---------- Board (idle list + session grid) ----------

    function renderBoard(board, mine) {
        const key = JSON.stringify([board, mine]);
        if (key === lastBoardKey) return;
        lastBoardKey = key;

        toolInfo = {};
        board.forEach(function (g) {
            g.units.forEach(function (u) {
                toolInfo[String(u.tool_id)] = { photo: g.photo_url, typeName: g.type_name };
            });
        });

        const sum = summarize(board, mine);
        const countText = sum.present + ' dari ' + sum.total + ' unit';
        $('rack-count').textContent = countText;
        $('grid-count').textContent = countText;

        const list = $('rack-list');
        const grid = $('rack-grid');
        list.textContent = '';
        grid.textContent = '';
        if (!sum.groups.length) {
            list.appendChild(h('li', { class: 'empty', text: 'Belum ada alat terdaftar.' }));
            grid.appendChild(h('li', { class: 'empty', text: 'Belum ada alat terdaftar.' }));
        }
        sum.groups.forEach(function (g) {
            list.appendChild(h('li', { class: 'rack-item' },
                toolPhoto(g.photo, g.name, 'sm'),
                h('div', { class: 'rack-item__text' },
                    h('div', { class: 'rack-item__name', text: g.name }),
                    unitsEl(g.marks, false),
                    countEl(g))));
            grid.appendChild(h('li', { class: 'rack-tile' },
                toolPhoto(g.photo, g.name, 'md'),
                h('div', { class: 'rack-tile__name', text: g.name }),
                unitsEl(g.marks, true)));
        });
        legendInto($('rack-legend'), sum.used);
        legendInto($('grid-legend'), sum.used);
    }

    function renderUnverified(rows) {
        const key = JSON.stringify(rows);
        if (key === lastUnverifiedKey) return;
        lastUnverifiedKey = key;
        const list = $('unverified-list');
        list.textContent = '';
        rows.forEach(function (r) {
            list.appendChild(h('li', null,
                h('strong', { text: r.tool_name }),
                ' · ' + (r.borrower_name || '-') + ' · ' + UI.formatWibTime(r.return_time)));
        });
        $('unverified').hidden = rows.length === 0;
    }

    // ---------- Transactions of this session ----------

    function txnRow(it, returned) {
        const info = toolInfo[String(it.tool_id)] || {};
        let meta;
        if (returned) {
            meta = h('div', { class: 'txn__meta txn__meta--muted', text: 'Sudah kembali di rak' });
        } else if (it.due_at) {
            meta = h('div', { class: 'txn__meta' }, 'Kembalikan paling lambat ',
                h('strong', { text: UI.formatWibDay(it.due_at) }));
        }
        return h('li', { class: 'txn' },
            toolPhoto(info.photo, info.typeName || it.tool_name, 'lg'),
            h('div', { class: 'txn__text' },
                h('div', { class: 'txn__name', text: it.tool_name }),
                meta || null,
                it.late_identify ? h('div', { class: 'txn__meta txn__meta--muted', text: 'Dicatat setelah alarm' }) : null),
            h('span', {
                class: 'txn__tag' + (returned ? ' txn__tag--muted' : ''),
                text: returned ? 'dikembalikan' : 'baru saja',
            }));
    }

    function txnGroup(title, items, returned, small) {
        const ul = h('ul', { class: 'txn-list' });
        items.forEach(function (it) { ul.appendChild(txnRow(it, returned)); });
        return h('section', { class: 'txn-group' },
            h(small ? 'h2' : 'h1', { class: 'txn-group__title' + (small ? ' txn-group__title--sm' : ''), text: title }),
            ul);
    }

    function renderLists(s, summary) {
        const borrowed = s.borrowed || [];
        const returned = s.returned || [];
        const name = (s.student && s.student.name) || '';
        const key = JSON.stringify([summary, name, borrowed, returned, Object.keys(toolInfo).length]);
        if (key === lastListsKey) return;
        lastListsKey = key;

        const box = $('ses-lists');
        box.textContent = '';
        if (summary) {
            box.appendChild(h('h1', { class: 'txn-group__title', text: 'Selesai. Terima kasih, ' + name }));
            if (borrowed.length) box.appendChild(txnGroup('Anda pinjam', borrowed, false, true));
            if (returned.length) box.appendChild(txnGroup('Anda kembalikan', returned, true, true));
            if (!borrowed.length && !returned.length) {
                box.appendChild(h('p', { class: 'session-hint', text: 'Tidak ada alat yang dipinjam atau dikembalikan.' }));
            }
            return;
        }
        if (borrowed.length || !returned.length) {
            const g = txnGroup('Anda pinjam', borrowed, false, false);
            if (!borrowed.length) {
                g.querySelector('ul').appendChild(h('li', { class: 'txn session-hint', text: 'Belum ada alat yang diambil.' }));
            }
            box.appendChild(g);
        }
        if (returned.length) box.appendChild(txnGroup('Anda kembalikan', returned, true, !!borrowed.length));
        else if (borrowed.length) {
            box.appendChild(h('p', { class: 'session-hint', text: 'Alat yang Anda kembalikan di sesi ini akan muncul di sini juga.' }));
        }
    }

    // ---------- Screens ----------

    function photoOf(student) {
        return (student && student.photo_url) || CFG.placeholderPhoto;
    }

    function setPhoto(img, student) {
        const src = photoOf(student);
        if (img.getAttribute('src') !== src) {
            img.onerror = function () { img.onerror = null; img.src = CFG.placeholderPhoto; };
            img.src = src;
        }
        img.alt = student ? 'Foto ' + student.name : '';
    }

    function fmtLeft(sec) {
        const s = Math.max(0, Math.ceil(sec || 0));
        return Math.floor(s / 60) + '.' + String(s % 60).padStart(2, '0');
    }

    function showScreen(state) {
        let screen = null;
        document.querySelectorAll('[data-screen]').forEach(function (el) {
            const on = el.getAttribute('data-screen').split(' ').indexOf(state) >= 0;
            el.hidden = !on;
            if (on) {
                screen = el;
                el.querySelectorAll('[data-view]').forEach(function (v) {
                    v.hidden = v.getAttribute('data-view') !== state;
                });
            }
        });
        $('kiosk').setAttribute('data-state', state);
        return screen;
    }

    function renderIdle(s) {
        const box = $('idle-reason');
        if (s.reason && lastState && lastState !== 'idle') reasonShownAt = Date.now();
        const show = s.state === 'idle' && s.reason && REASONS[s.reason] && Date.now() - reasonShownAt < REASON_SHOW_MS;
        box.hidden = !show;
        if (show) box.textContent = REASONS[s.reason];
        if (s.state === 'unknown_face') {
            $('unknown-ends').textContent = 'Kembali ke layar awal dalam ' + Math.ceil(s.unknown_ends_in || 0) + ' detik';
        }
    }

    function renderIdentifying(s) {
        const st = s.student || {};
        setPhoto($('id-photo'), st);
        $('id-name').textContent = st.name || '';
        $('id-nim').textContent = st.nim || '';
        const steps = s.steps || 2;
        const step = s.step || 1;
        const bar = $('id-steps');
        if (bar.childElementCount !== steps || bar.getAttribute('data-step') !== String(step)) {
            bar.textContent = '';
            for (let i = 1; i <= steps; i++) bar.appendChild(h('span', { class: i <= step ? 'is-on' : '' }));
            bar.setAttribute('data-step', String(step));
            bar.setAttribute('aria-label', 'Langkah ' + step + ' dari ' + steps);
        }
        const turn = TURNS[s.direction] || TURNS.left;
        const other = turn === TURNS.left ? TURNS.right : TURNS.left;
        $('id-step-label').textContent = 'Langkah ' + step + ' dari ' + steps + ' · memastikan Anda hadir';
        $('id-turn-text').textContent = turn.text;
        // The two steps are the two directions, so the next one is the other.
        $('id-help').textContent = 'Putar kepala pelan ke arah panah, lalu kembali menghadap kamera.' +
            (step < steps ? ' Setelah itu ' + other.text.toLowerCase() + '.' : '');
        return turn;
    }

    function renderPerson(s) {
        const st = s.student || {};
        $('ses-name').textContent = st.name || '';
        $('ses-nim').textContent = st.nim || '';
    }

    function render(s) {
        const state = STATES.indexOf(s.state) >= 0 ? s.state : 'idle';
        const screen = showScreen(state);
        let mode = 'guide';
        const opts = {};
        if (state === 'idle' || state === 'unknown_face') {
            renderIdle(s);
        } else if (state === 'identifying') {
            mode = 'turn';
            opts.toLeft = renderIdentifying(s).toLeft;
        } else {
            renderPerson(s);
            renderLists(s, state === 'summary');
            opts.small = true;
            if (state === 'session') {
                mode = 'ok';
                $('ses-left').textContent = fmtLeft(s.expires_in);
                $('btn-cancel').hidden = !s.can_cancel;
            } else {
                $('sum-ends').textContent = 'Kembali ke layar awal dalam ' + Math.ceil(s.summary_ends_in || 0) + ' detik';
            }
        }
        lastState = state;

        const alarms = s.alarms || [];
        const compact = state !== 'idle' && state !== 'unknown_face';
        renderAlarm(alarms, compact);
        // Full alarm: the camera moves into it, so the borrower can still look
        // at the camera to record the borrow.
        if (alarms.length && !compact) placeCamera($('alarm').querySelector('[data-camera-slot]'), 'guide', {});
        else placeCamera(screen && screen.querySelector('[data-camera-slot]'), mode, opts);
    }

    // ---------- Alarm ----------

    function renderAlarm(alarms, compact) {
        const box = $('alarm');
        alarmIds = alarms.map(function (a) { return a.alarm_id; });
        if (!alarms.length) {
            box.hidden = true;
            closeAdmin();
            lastAlarmKey = '';
            document.documentElement.style.setProperty('--alarm-bar-h', '0px');
            return;
        }
        // A student at the kiosk keeps the screen; the alarm becomes a bottom bar.
        box.classList.toggle('alarm--compact', compact);
        box.hidden = false;
        const key = JSON.stringify(alarms) + Object.keys(toolInfo).length;
        if (key !== lastAlarmKey) {
            lastAlarmKey = key;
            renderAlarmList(alarms);
        }
        document.documentElement.style.setProperty('--alarm-bar-h', compact ? box.offsetHeight + 'px' : '0px');
    }

    function renderAlarmList(alarms) {
        const list = $('alarm-list');
        list.textContent = '';
        $('alarm-count').textContent = alarms.length + ' alat';
        alarms.forEach(function (a) {
            const name = a.tool_name || 'Alat #' + a.tool_id;
            const info = toolInfo[String(a.tool_id)] || {};
            list.appendChild(h('li', { class: 'alarm__item' },
                toolPhoto(info.photo, info.typeName || name, 'lg'),
                h('div', { class: 'txn__text' },
                    h('div', { class: 'txn__name', text: name }),
                    h('div', { class: 'alarm__since', text: 'sejak ' + UI.formatWibTime(a.started_at) }))));
        });
    }

    function openAdmin() {
        $('alarm-admin-btn').hidden = true;
        $('alarm-admin-form').hidden = false;
        $('alarm-error').textContent = '';
        $('alarm-pin').value = '';
        $('alarm-pin').focus();
    }

    function closeAdmin() {
        $('alarm-admin-btn').hidden = false;
        $('alarm-admin-form').hidden = true;
        $('alarm-pin').value = '';
    }

    async function ackAlarms(ev) {
        ev.preventDefault();
        const pin = $('alarm-pin').value;
        if (!pin) return;
        const err = $('alarm-error');
        err.textContent = '';
        try {
            const login = await UI.postJSON('/api/admin/login', { pin: pin });
            if (!login.success) {
                err.textContent = login.error || 'PIN salah';
                $('alarm-pin').select();
                return;
            }
            const ids = alarmIds.slice();
            let failed = 0;
            for (let i = 0; i < ids.length; i++) {
                const res = await UI.postJSON('/api/alarms/' + ids[i] + '/ack');
                if (!res.success) failed += 1;
            }
            // Do not leave the kiosk browser logged in as admin.
            await fetch('/admin/logout', { credentials: 'same-origin', redirect: 'manual' });
            closeAdmin();
            if (failed) UI.toast(failed + ' alarm tidak dapat dimatikan.', 'warn');
            else UI.toast('Alarm dimatikan oleh admin.', 'ok');
            poll();
        } catch (e) {
            err.textContent = 'Tidak dapat menghubungi server.';
        }
    }

    // ---------- Actions ----------

    async function act(url, button) {
        button.disabled = true;
        try {
            const res = await UI.postJSON(url);
            if (!res.success) UI.toast(res.error || 'Permintaan gagal', 'danger');
        } catch (e) {
            UI.toast('Tidak dapat menghubungi server.', 'danger');
        } finally {
            button.disabled = false;
            poll();
        }
    }

    // ---------- Poll ----------

    let pollTimer = null;
    let inFlight = false;

    function mineOf(s) {
        const mine = {};
        if (s.state === 'session' || s.state === 'summary') {
            (s.borrowed || []).forEach(function (b) { mine[String(b.tool_id)] = true; });
        }
        return mine;
    }

    // One poll chain; an extra call (after a button) just polls early.
    async function poll() {
        if (inFlight) return;
        clearTimeout(pollTimer);
        inFlight = true;
        try {
            const s = await UI.fetchJSON('/api/kiosk/state');
            if (s.success) {
                if (serverDown) {
                    serverDown = false;
                    renderBanners();
                }
                renderBoard(s.board || [], mineOf(s));
                renderUnverified(s.unverified_returns || []);
                render(s);
            }
        } catch (e) {
            if (!serverDown) {
                serverDown = true;
                renderBanners();
            }
        } finally {
            inFlight = false;
            pollTimer = setTimeout(poll, POLL_MS);
        }
    }

    // ---------- Init ----------

    document.addEventListener('DOMContentLoaded', function () {
        tickClock();
        setInterval(tickClock, 1000);
        startCamera();
        placeCamera(showScreen('idle').querySelector('[data-camera-slot]'), 'guide', {});
        $('btn-end').addEventListener('click', function () { act('/api/kiosk/end', $('btn-end')); });
        $('btn-cancel').addEventListener('click', function () { act('/api/kiosk/cancel', $('btn-cancel')); });
        $('alarm-admin-btn').addEventListener('click', openAdmin);
        $('alarm-admin-close').addEventListener('click', closeAdmin);
        $('alarm-admin-form').addEventListener('submit', ackAlarms);
        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape') closeAdmin();
        });
        poll();
        pollDevices();
    });
})();
