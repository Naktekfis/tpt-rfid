/*
 * /admin dashboard: today's date, four counters, "Perlu tindakan" (alarms,
 * unverified returns, overdue loans) and device state. Polls every 10 s.
 */
(function () {
    'use strict';

    const UI = window.UI;
    const h = UI.h;
    const POLL_MS = 10000;
    const MONITOR = '/admin/monitor';
    const CONDITIONS = {
        disabled: 'Dinonaktifkan', warming_up: 'Memeriksa…', healthy: 'Normal', unavailable: 'Tidak tersedia',
        suspected_obstruction: 'Dugaan tertutup / cahaya kurang', camera_unavailable: 'Tidak tersedia',
        camera_suspected_obstruction: 'Dugaan tertutup / cahaya kurang',
    };
    const $ = function (id) { return document.getElementById(id); };

    $('hero-date').textContent = new Intl.DateTimeFormat('id-ID', {
        timeZone: 'Asia/Jakarta', weekday: 'long', day: 'numeric', month: 'long', year: 'numeric',
    }).format(new Date());

    // Resolves to the response, or null after a redirect to the login page.
    async function get(url) {
        const res = await UI.fetchJSON(url);
        if (res.error === 'Unauthorized') {
            window.location.href = '/admin/login';
            return null;
        }
        if (!res.success) throw new Error(res.error || 'Data tidak dapat dimuat');
        return res;
    }

    function item(title, meta, danger) {
        return h('li', null, h('a', { href: MONITOR },
            h('strong', { class: danger ? 'status status--danger' : 'status status--warn', text: title }),
            h('span', { class: 'sub', text: meta })));
    }

    // The tile turns red/amber only while its count is above zero.
    function setStat(id, n) {
        $(id).textContent = n;
        $(id).parentNode.classList.toggle('stat--on', n > 0);
    }

    function renderAlerts(alerts, tools) {
        const alarms = alerts.alarms || [];
        const returns = alerts.unverified_returns || [];
        const borrowed = tools.filter(function (t) { return t.status === 'borrowed'; });
        const overdue = borrowed.filter(function (t) { return t.is_overdue; });
        setStat('stat-alarms', alarms.length);
        setStat('stat-unverified', returns.length);
        setStat('stat-borrowed', borrowed.length);
        setStat('stat-overdue', overdue.length);

        const list = $('todo-list');
        list.textContent = '';
        alarms.forEach(function (a) {
            list.appendChild(item('Alarm · ' + (a.tool_name || 'Alat #' + a.tool_id), 'Sejak ' + UI.formatWibDate(a.started_at), true));
        });
        returns.forEach(function (r) {
            list.appendChild(item('Belum diverifikasi · ' + r.tool_name,
                (r.borrower_name || '-') + ' · kembali ' + UI.formatWibDate(r.return_time), false));
        });
        overdue.forEach(function (t) {
            list.appendChild(item('Terlambat · ' + t.name, (t.borrower_name || '-') + ' · batas ' + UI.formatWibDate(t.due_at, true), false));
        });
        if (!list.children.length) list.appendChild(h('li', { class: 'empty', text: 'Tidak ada yang perlu ditindaklanjuti.' }));
    }

    function renderDevices(devices, security) {
        const reader = devices.reader || {};
        $('dev-reader').textContent = reader.mode === 'mock' ? 'Simulasi' : (reader.connected ? 'Terhubung' : 'Tidak terhubung');
        $('dev-nfc').textContent = (devices.nfc || {}).mode === 'mock' ? 'Simulasi' : ((devices.nfc || {}).connected ? 'Terhubung' : 'Tidak terhubung');
        $('dev-camera').textContent = (devices.camera || {}).running ? 'Aktif' : 'Tidak aktif';
        $('dev-condition').textContent = CONDITIONS[security.condition] || security.condition || '–';
    }

    async function refresh() {
        try {
            const results = await Promise.all([
                get('/api/admin/kiosk/alerts'), get('/api/admin/tools_status'),
                get('/api/devices/status'), get('/api/admin/security'),
            ]);
            if (results.indexOf(null) !== -1) return;
            renderAlerts(results[0], results[1].tools || []);
            renderDevices(results[2], results[3]);
            UI.loadNotice('dash-error', '');
        } catch (e) {
            UI.loadNotice('dash-error', 'Data ringkasan belum dapat dimuat.', refresh);
        }
    }

    refresh();
    setInterval(refresh, POLL_MS);
})();
