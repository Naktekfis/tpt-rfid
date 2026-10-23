/*
 * Kiosk screen (design D): polls /api/kiosk/state every second and shows one
 * screen per kiosk state (idle / unknown_card, session /
 * summary) plus the alarm. The kiosk logic runs server-side; this page only
 * shows it and sends "Selesai" / "Bukan saya" / admin alarm acknowledge.
 */
(function () {
    'use strict';

    const UI = window.UI;
    const h = UI.h;

    const POLL_MS = 500;
    const DEVICE_POLL_MS = 5000;
    const REASON_SHOW_MS = 8000;
    const STATES = ['idle', 'unknown_card', 'session', 'summary'];

    const REASONS = {
        cancelled: 'Sesi dibatalkan. Tidak ada alat yang tercatat.',
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
    let summaryExitTimer = null;
    let summaryExpiredAt = null;
    let alarmIds = [];
    let serverDown = false;
    let devices = null;
    let lastBannersKey = '';
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
        const key = JSON.stringify([serverDown, devices && devices.reader && devices.reader.connected, devices && devices.reader && devices.reader.mode, devices && devices.nfc && devices.nfc.connected]);
        if (key === lastBannersKey) return;
        lastBannersKey = key;
        box.textContent = '';
        if (serverDown) {
            box.appendChild(h('div', { class: 'bar bar--danger', role: 'alert' },
                'Data belum dapat diperbarui. Tunggu koneksi pulih sebelum mengambil atau mengembalikan alat. Mencoba kembali otomatis…'));
            return;
        }
        if (!devices) return;
        const r = devices.reader || {};
        const n = devices.nfc || {};
        if (r.mode === 'vx6336' && !r.connected) {
            box.appendChild(h('div', { class: 'bar bar--warn', role: 'status' },
                'Pembaca RFID tidak terhubung. Peminjaman dan pengembalian belum tercatat sampai pembaca tersambung kembali.'));
        }
        if (n.connected === false) {
            box.appendChild(h('div', { class: 'bar bar--warn', role: 'status' },
                'Pembaca NFC tidak terhubung. Sesi baru belum dapat dibuka. Hubungi admin.'));
        }
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
            row.appendChild(h('span', { class: 'unit-mark unit-mark--' + m.kind, title: m.title, role: 'img', 'aria-label': m.title }));
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
        if (s.state === 'unknown_card') {
            $('unknown-ends').textContent = 'Kembali ke layar awal dalam ' + Math.ceil(s.unknown_ends_in || 0) + ' detik';
        }
    }

    function renderPerson(s) {
        const st = s.student || {};
        $('ses-name').textContent = st.name || '';
        $('ses-nim').textContent = st.nim || '';
    }

    function render(s) {
        const state = STATES.indexOf(s.state) >= 0 ? s.state : 'idle';
        if (state !== 'summary') summaryExpiredAt = null;
        clearTimeout(summaryExitTimer);
        summaryExitTimer = null;
        showScreen(state);
        if (state === 'idle' || state === 'unknown_card') {
            renderIdle(s);
        } else {
            renderPerson(s);
            renderLists(s, state === 'summary');
            if (state === 'session') {
                $('ses-left').textContent = fmtLeft(s.expires_in);
                $('btn-cancel').hidden = !s.can_cancel;
            } else {
                $('sum-ends').textContent = 'Kembali ke layar awal dalam ' + Math.ceil(s.summary_ends_in || 0) + ' detik';
                // The API rounds this value to 0.1 s. Leave the summary at
                // its actual deadline instead of waiting for the next poll.
                const remaining = Math.max(0, Number(s.summary_ends_in) || 0);
                summaryExitTimer = setTimeout(function () {
                    if (lastState !== 'summary') return;
                    summaryExpiredAt = performance.now();
                    showScreen('idle');
                    renderIdle({ state: 'idle', reason: null });
                    lastState = 'idle';
                    poll();
                }, remaining * 1000 + 60);
            }
        }
        lastState = state;

        const alarms = s.alarms || [];
        const compact = state !== 'idle' && state !== 'unknown_card';
        renderAlarm(alarms, compact);

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
        const label = button.textContent;
        button.textContent = 'Memproses…';
        button.setAttribute('aria-busy', 'true');
        try {
            const res = await UI.postJSON(url);
            if (!res.success) UI.toast(res.error || 'Permintaan gagal', 'danger');
        } catch (e) {
            UI.toast('Tidak dapat menghubungi server.', 'danger');
        } finally {
            button.disabled = false;
            button.textContent = label;
            button.removeAttribute('aria-busy');
            poll();
        }
    }

    // ---------- Poll ----------

    let pollTimer = null;
    let inFlight = false;
    // Opt-in, local-only aggregate diagnostics; never retain state payloads.
    const timingEnabled = new URLSearchParams(window.location.search).get('uhf_timing') === '1';
    const timingSamples = [];
    let previousPollEnd = null;
    if (timingEnabled) {
        window.kioskTiming = function () {
            const result = { samples: timingSamples.length, poll_ms: POLL_MS };
            ['schedule_wait_ms', 'request_ms', 'dom_ms', 'next_frame_ms'].forEach(function (key) {
                const values = timingSamples.map(function (s) { return s[key]; })
                    .filter(function (v) { return Number.isFinite(v); }).sort(function (a, b) { return a - b; });
                result[key] = values.length ? {
                    samples: values.length,
                    mean: values.reduce(function (a, b) { return a + b; }, 0) / values.length,
                    p95: values[Math.ceil(values.length * 0.95) - 1],
                    max: values[values.length - 1],
                } : null;
            });
            result.failures = timingSamples.filter(function (s) { return s.failed; }).length;
            return result;
        };
    }

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
        const requestStarted = performance.now();
        const started = timingEnabled ? requestStarted : 0;
        const timing = timingEnabled ? {
            schedule_wait_ms: previousPollEnd === null ? null : started - previousPollEnd,
            failed: true,
        } : null;
        try {
            const s = await UI.fetchJSON('/api/kiosk/state');
            if (timing) timing.request_ms = performance.now() - started;
            if (!s.success) throw new Error('State unavailable');
            if (s.success) {
                // A response requested before the local deadline may arrive
                // after it; do not bring an expired summary back on screen.
                if (s.state === 'summary' && summaryExpiredAt !== null && requestStarted <= summaryExpiredAt) return;
                const domStarted = timingEnabled ? performance.now() : 0;
                if (serverDown) {
                    serverDown = false;
                    renderBanners();
                }
                renderBoard(s.board || [], mineOf(s));
                renderUnverified(s.unverified_returns || []);
                render(s);
                if (timing) {
                    timing.failed = false;
                    const domEnd = performance.now();
                    timing.dom_ms = domEnd - domStarted;
                    // Animation-frame boundary is a proxy, not proof of screen paint.
                    requestAnimationFrame(function () { timing.next_frame_ms = performance.now() - domEnd; });
                }
            }
        } catch (e) {
            if (!serverDown) {
                serverDown = true;
                renderBanners();
                if (!lastBoardKey) $('rack-list').querySelector('.empty').textContent = 'Data alat belum tersedia. Menunggu koneksi pulih…';
            }
        } finally {
            if (timing) {
                previousPollEnd = performance.now();
                timingSamples.push(timing);
                if (timingSamples.length > 120) timingSamples.shift();
            }
            inFlight = false;
            pollTimer = setTimeout(poll, POLL_MS);
        }
    }

    // ---------- Init ----------

    document.addEventListener('DOMContentLoaded', function () {
        tickClock();
        setInterval(tickClock, 1000);
        showScreen('idle');
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
