/*
 * Kiosk screen: polls /api/kiosk/state every second and renders the tool
 * board, the interaction panel (one view per kiosk state) and the alarm.
 * The kiosk logic runs server-side; this page only shows it and sends
 * "Selesai" / "Bukan saya" / admin alarm acknowledge.
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

    const TITLES = {
        idle: 'Selamat datang',
        identifying: 'Verifikasi wajah',
        unknown_face: 'Wajah tidak dikenali',
        session: 'Sesi peminjaman',
        summary: 'Ringkasan',
    };

    const REASONS = {
        challenge_timeout: 'Verifikasi belum selesai dalam waktu yang tersedia. Silakan lihat ke kamera untuk mencoba lagi.',
        different_face: 'Wajah yang terlihat berganti selama verifikasi. Silakan ulangi dari awal.',
        face_lost: 'Wajah tidak terlihat lagi oleh kamera. Silakan lihat ke kamera untuk mengulang.',
        cancelled: 'Sesi dibatalkan. Tidak ada alat yang tercatat.',
    };

    // Backend direction is in raw-image terms: "left" means the person turns
    // to their own right, which is the screen right in the mirrored preview.
    const TURNS = {
        left: { text: 'Tengok ke kanan', path: 'M4 12h15M13 6l6 6-6 6' },
        right: { text: 'Tengok ke kiri', path: 'M20 12H5M11 6l-6 6 6 6' },
    };

    const $ = function (id) { return document.getElementById(id); };

    let lastState = null;
    let lastBoardKey = '';
    let lastUnverifiedKey = '';
    let lastAlarmKey = '';
    let reasonShownAt = 0;
    let sessionMax = 0;
    let alarmIds = [];
    let serverDown = false;
    let devices = null;

    // ---------- Clock ----------

    const timeFmt = new Intl.DateTimeFormat('id-ID', {
        timeZone: 'Asia/Jakarta', hour: '2-digit', minute: '2-digit', hour12: false,
    });
    const dateFmt = new Intl.DateTimeFormat('id-ID', {
        timeZone: 'Asia/Jakarta', weekday: 'long', day: 'numeric', month: 'long', year: 'numeric',
    });

    function tickClock() {
        const now = new Date();
        $('clock-time').textContent = timeFmt.format(now).replace(':', '.') + ' WIB';
        $('clock-date').textContent = dateFmt.format(now);
    }

    // ---------- Banners ----------

    function renderBanners() {
        const box = $('banners');
        box.textContent = '';
        if (serverDown) {
            box.appendChild(h('div', { class: 'banner banner--danger', role: 'alert' },
                'Koneksi ke server terputus. Data di layar mungkin tidak terbaru.'));
            return;
        }
        if (!devices) return;
        const r = devices.reader || {};
        const c = devices.camera || {};
        if (r.mode === 'serial' && !r.connected) {
            box.appendChild(h('div', { class: 'banner', role: 'status' },
                'Pembaca RFID tidak terhubung. Peminjaman dan pengembalian belum tercatat sampai pembaca tersambung kembali.'));
        }
        if (c.enabled && !cameraOk(c)) {
            box.appendChild(h('div', { class: 'banner', role: 'status' },
                'Kamera tidak mengirim gambar. Pengenalan wajah tidak berjalan.'));
        }
    }

    function cameraOk(c) {
        return !!(c.enabled && c.running && c.opened && c.frame_age !== null && c.frame_age < 3);
    }

    function setDot(el, kind, label) {
        el.className = 'dot-status' + (kind ? ' dot-status--' + kind : '');
        el.textContent = label;
    }

    function renderDevices() {
        const r = (devices && devices.reader) || {};
        const c = (devices && devices.camera) || {};
        if (!devices) {
            setDot($('dev-reader'), '', 'Pembaca RFID');
            setDot($('dev-camera'), '', 'Kamera');
        } else {
            if (r.mode === 'mock') setDot($('dev-reader'), 'warn', 'Pembaca RFID: simulasi');
            else if (r.connected) setDot($('dev-reader'), 'ok', 'Pembaca RFID: terhubung');
            else setDot($('dev-reader'), 'danger', 'Pembaca RFID: terputus');

            if (!c.enabled) setDot($('dev-camera'), 'warn', 'Kamera: tidak aktif');
            else if (cameraOk(c)) setDot($('dev-camera'), 'ok', 'Kamera: aktif');
            else setDot($('dev-camera'), 'danger', 'Kamera: tidak ada gambar');
        }
        renderBanners();
    }

    async function pollDevices() {
        try {
            const data = await UI.fetchJSON('/api/devices/status');
            if (data.success) devices = data;
        } catch (e) {
            devices = null;
        }
        renderDevices();
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

    function placeCamera(view, small) {
        const cam = $('camera');
        const slot = view ? view.querySelector('[data-camera-slot]') : null;
        if (!slot) {
            cam.hidden = true;
            return;
        }
        if (cam.parentNode !== slot) slot.appendChild(cam);
        cam.classList.toggle('camera--small', !!small);
        cam.hidden = false;
    }

    // ---------- Board ----------

    function unitStatus(u) {
        if (u.status === 'borrowed') {
            return u.is_overdue ? { kind: 'warn', label: 'Terlambat' } : { kind: 'info', label: 'Dipinjam' };
        }
        if (u.status === 'available') {
            if (u.presence === 'present') return { kind: 'ok', label: 'Tersedia' };
            if (u.presence === 'missing') return { kind: 'danger', label: 'Tidak terdeteksi' };
            return { kind: '', label: 'Belum terbaca' };
        }
        return { kind: '', label: u.status === 'maintenance' ? 'Perawatan' : (u.status || 'Tidak diketahui') };
    }

    function renderBoard(board) {
        const key = JSON.stringify(board);
        if (key === lastBoardKey) return;
        lastBoardKey = key;

        const counts = { ok: 0, info: 0, warn: 0, danger: 0 };
        const body = $('board');
        body.textContent = '';
        if (!board.length) {
            body.appendChild(h('p', { class: 'empty', text: 'Belum ada alat terdaftar.' }));
        }
        board.forEach(function (group) {
            let available = 0;
            const units = h('div', { class: 'units' });
            group.units.forEach(function (u) {
                const st = unitStatus(u);
                if (counts[st.kind] !== undefined) counts[st.kind] += 1;
                if (st.kind === 'ok') available += 1;
                const tile = h('div', { class: 'unit' + (st.kind ? ' unit--' + st.kind : ''), title: u.name },
                    h('div', { class: 'unit__top' },
                        h('span', { class: 'unit__no', text: u.unit_no ? '#' + u.unit_no : u.name }),
                        h('span', { class: 'pill' + (st.kind ? ' pill--' + st.kind : ''), text: st.label })));
                if (u.status === 'borrowed') {
                    tile.appendChild(h('div', { class: 'unit__who', text: u.borrower_name || 'Peminjam tidak diketahui' }));
                    if (u.borrower_nim) tile.appendChild(h('div', { class: 'unit__nim mono', text: u.borrower_nim }));
                    if (u.due_at) {
                        tile.appendChild(h('div', {
                            class: 'unit__meta',
                            text: (u.is_overdue ? 'Batas ' : 'Kembali ') + UI.formatWibDate(u.due_at, true),
                        }));
                    }
                } else if (st.kind === 'danger') {
                    tile.appendChild(h('div', { class: 'unit__meta', text: 'Tidak terbaca di rak' }));
                }
                units.appendChild(tile);
            });
            body.appendChild(h('section', { class: 'tool-group' },
                h('div', { class: 'tool-group__head' },
                    h('h3', { text: group.type_name }),
                    h('span', { class: 'tool-group__count', text: available + ' dari ' + group.units.length + ' tersedia' })),
                units));
        });

        const summary = $('board-summary');
        summary.textContent = '';
        [['ok', 'Tersedia'], ['info', 'Dipinjam'], ['warn', 'Terlambat'], ['danger', 'Tidak terdeteksi']]
            .forEach(function (pair) {
                if (pair[0] !== 'ok' && pair[0] !== 'info' && !counts[pair[0]]) return;
                summary.appendChild(h('span', null, pair[1] + ' ', h('strong', { text: String(counts[pair[0]]) })));
            });
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
                ' · ' + (r.borrower_name || '-') + ' ',
                h('span', { class: 'muted mono', text: UI.formatWibTime(r.return_time) })));
        });
        $('unverified').hidden = rows.length === 0;
    }

    // ---------- Interaction panel ----------

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
        return Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0');
    }

    function fillList(ul, badge, items, withDue, emptyText) {
        ul.textContent = '';
        badge.textContent = String(items.length);
        if (!items.length) {
            ul.appendChild(h('li', { class: 'empty', text: emptyText }));
            return;
        }
        items.forEach(function (it) {
            const meta = withDue && it.due_at ? 'Kembalikan sebelum ' + UI.formatWibDate(it.due_at) : null;
            ul.appendChild(h('li', null,
                h('div', { class: 'item-name', text: it.tool_name }),
                meta ? h('div', { class: 'item-meta', text: meta }) : null,
                it.late_identify ? h('div', { class: 'item-meta', text: 'Dicatat setelah alarm' }) : null));
        });
    }

    function showView(state) {
        let current = null;
        document.querySelectorAll('[data-view]').forEach(function (v) {
            const on = v.getAttribute('data-view') === state;
            v.hidden = !on;
            if (on) current = v;
        });
        $('interact-title').textContent = TITLES[state] || TITLES.idle;
        placeCamera(current, state === 'identifying');
        return current;
    }

    function renderIdentifying(s) {
        const st = s.student || {};
        setPhoto($('id-photo'), st);
        $('id-name').textContent = st.name || '';
        $('id-nim').textContent = st.nim || '';
        const steps = s.steps || 2;
        const step = s.step || 1;
        const bar = $('id-steps');
        bar.textContent = '';
        for (let i = 1; i <= steps; i++) {
            bar.appendChild(h('span', { class: i < step ? 'is-done' : (i === step ? 'is-current' : '') }));
        }
        $('id-step-label').textContent = 'Langkah ' + step + ' dari ' + steps;
        const turn = TURNS[s.direction] || TURNS.left;
        $('id-arrow').setAttribute('d', turn.path);
        $('id-turn-text').textContent = turn.text;
    }

    function renderSession(s) {
        const st = s.student || {};
        setPhoto($('ses-photo'), st);
        $('ses-name').textContent = st.name || '';
        $('ses-nim').textContent = st.nim || '';
        const left = s.expires_in || 0;
        if (lastState !== 'session' || left > sessionMax) sessionMax = left;
        $('ses-left').textContent = fmtLeft(left);
        $('ses-fill').style.width = (sessionMax ? Math.min(100, (left / sessionMax) * 100) : 0) + '%';
        fillList($('ses-borrowed'), $('ses-borrowed-n'), s.borrowed || [], true, 'Belum ada alat diambil');
        fillList($('ses-returned'), $('ses-returned-n'), s.returned || [], false, 'Belum ada alat dikembalikan');
        $('btn-cancel').hidden = !s.can_cancel;
    }

    function renderSummary(s) {
        const st = s.student || {};
        $('sum-name').textContent = st.name || '';
        fillList($('sum-borrowed'), $('sum-borrowed-n'), s.borrowed || [], true, 'Tidak ada');
        fillList($('sum-returned'), $('sum-returned-n'), s.returned || [], false, 'Tidak ada');
        $('sum-ends').textContent = 'Kembali ke layar awal dalam ' + Math.ceil(s.summary_ends_in || 0) + ' detik.';
    }

    function renderIdle(s) {
        const box = $('idle-reason');
        if (s.reason && lastState && lastState !== 'idle') reasonShownAt = Date.now();
        const show = s.reason && REASONS[s.reason] && Date.now() - reasonShownAt < REASON_SHOW_MS;
        box.hidden = !show;
        if (show) box.textContent = REASONS[s.reason];
    }

    function renderPanel(s) {
        const state = TITLES[s.state] ? s.state : 'idle';
        showView(state);
        if (state === 'idle') renderIdle(s);
        else if (state === 'identifying') renderIdentifying(s);
        else if (state === 'unknown_face') {
            $('unknown-ends').textContent = 'Kembali ke layar awal dalam ' + Math.ceil(s.unknown_ends_in || 0) + ' detik.';
        } else if (state === 'session') renderSession(s);
        else if (state === 'summary') renderSummary(s);
        lastState = state;
    }

    // ---------- Alarm ----------

    function renderAlarm(alarms, state) {
        const box = $('alarm');
        alarmIds = alarms.map(function (a) { return a.alarm_id; });
        if (!alarms.length) {
            box.hidden = true;
            document.body.classList.remove('has-alarm-bar');
            closeAdmin();
            lastAlarmKey = '';
            return;
        }
        // A student at the kiosk keeps seeing the panel; the alarm becomes a bar.
        const compact = state !== 'idle' && state !== 'unknown_face';
        box.classList.toggle('alarm--compact', compact);
        box.hidden = false;
        // Full alarm: the camera preview moves into it, so the borrower can
        // still look at the camera to record the borrow.
        if (!compact) placeCamera(box, false);
        document.body.classList.toggle('has-alarm-bar', compact);
        const key = JSON.stringify(alarms);
        if (key !== lastAlarmKey) {
            lastAlarmKey = key;
            renderAlarmList(alarms);
        }
        // Keep the page content clear of the bottom bar.
        document.documentElement.style.setProperty('--alarm-bar-h', compact ? box.offsetHeight + 'px' : '0px');
    }

    function renderAlarmList(alarms) {
        const list = $('alarm-list');
        list.textContent = '';
        alarms.forEach(function (a) {
            list.appendChild(h('li', null,
                h('span', { text: a.tool_name || 'Alat #' + a.tool_id }),
                h('span', { class: 'mono', text: 'sejak ' + UI.formatWibTime(a.started_at) })));
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
                renderBoard(s.board || []);
                renderUnverified(s.unverified_returns || []);
                renderPanel(s);
                renderAlarm(s.alarms || [], s.state);
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
        showView('idle');
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
