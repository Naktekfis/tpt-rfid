(function () {
    'use strict';
    const h = UI.h;
    const labels = {
        disabled: 'Pemantauan kamera dinonaktifkan', warming_up: 'Memeriksa kamera…',
        healthy: 'Kamera normal', unavailable: 'Kamera tidak tersedia',
        suspected_obstruction: 'Dugaan tertutup / cahaya kurang',
        camera_unavailable: 'Kamera tidak tersedia',
        camera_suspected_obstruction: 'Dugaan tertutup / cahaya kurang',
    };
    const photos = {
        pending: 'Foto sedang diproses', camera_unavailable: 'Kamera tidak tersedia',
        storage_full: 'Penyimpanan foto penuh', capture_failed: 'Pengambilan foto gagal',
        queue_full: 'Antrean foto penuh',
    };
    function date(value) {
        if (!value) return '—';
        return new Date(value).toLocaleString('id-ID', { timeZone: 'Asia/Jakarta' });
    }
    function alarmDate(value) { return value ? UI.formatWibDate(value) : '—'; }
    async function refresh() {
        try {
            const result = await UI.fetchJSON('/api/admin/security');
            if (!result.success) throw new Error(result.error || 'Data tidak dapat dimuat');
            const storageMessage = document.getElementById('security-error');
            storageMessage.hidden = !result.evidence_storage_error;
            storageMessage.textContent = 'Penyimpanan dokumentasi bermasalah. Alarm suara tetap aktif; penyimpanan akan dicoba kembali.';
            const condition = document.getElementById('security-condition');
            condition.textContent = labels[result.condition] || result.condition;
            const alarmMap = {};
            (result.alarms || []).forEach(function (a) { alarmMap[a.alarm_id] = a; });
            const rows = result.events || [];
            const seen = {};
            const body = document.getElementById('security-events');
            body.textContent = '';
            rows.forEach(function (event) {
                const alarm = alarmMap[event.alarm_id];
                if (event.alarm_id) seen[event.alarm_id] = true;
                const title = event.kind === 'tool_alarm' ? 'Alarm alat · ' + (event.tool_name || 'Alat #' + event.tool_id) : labels[event.kind];
                let photo = h('span', { text: photos[event.photo_status] || 'Foto tidak tersedia' });
                if (event.photo_status === 'captured') {
                    photo = h('a', { href: '/api/admin/security/events/' + event.event_id + '/photo', target: '_blank', rel: 'noopener', text: 'Lihat foto' });
                }
                const resolved = alarm ? (alarm.ended_at ? 'Selesai · ' + (alarm.ended_by || '') + ' · ' + alarmDate(alarm.ended_at) : 'Alarm alat terbuka')
                    : (event.recovered_at ? (event.recovery_reason === 'healthy' ? 'Kamera pulih · ' : 'Kondisi berubah · ') + date(event.recovered_at) : 'Gangguan masih aktif');
                const action = event.acknowledged_at ? h('span', { text: 'Diperiksa · ' + date(event.acknowledged_at) })
                    : h('button', { type: 'button', class: 'btn btn--secondary btn--sm', text: 'Tandai diperiksa' });
                if (!event.acknowledged_at) action.addEventListener('click', async function () {
                    action.disabled = true;
                    try {
                        const response = await UI.postJSON('/api/admin/security/events/' + event.event_id + '/ack', {});
                        if (!response.success) throw new Error(response.error);
                        refresh();
                    } catch (error) { UI.toast('Kejadian gagal diperbarui.', 'danger'); }
                    finally { action.disabled = false; }
                });
                body.appendChild(h('tr', null, h('td', { text: title }), h('td', { class: 'num', text: date(event.started_at) }),
                    h('td', null, photo), h('td', { text: resolved }), h('td', null, action)));
            });
            (result.alarms || []).filter(function (alarm) { return !seen[alarm.alarm_id]; }).forEach(function (alarm) {
                body.appendChild(h('tr', null,
                    h('td', { text: 'Alarm alat · ' + alarm.tool_name }), h('td', { text: alarmDate(alarm.started_at) }),
                    h('td', { text: 'Belum ada dokumentasi foto' }),
                    h('td', { text: alarm.ended_at ? 'Selesai · ' + alarm.ended_by : 'Alarm alat terbuka' }), h('td', { text: '—' })));
            });
            if (!body.children.length) body.appendChild(h('tr', null, h('td', { colspan: '5', class: 'empty', text: 'Belum ada kejadian keamanan.' })));
        } catch (error) {
            const message = document.getElementById('security-error');
            message.textContent = 'Data keamanan gagal dimuat. Periksa koneksi atau masuk kembali sebagai admin.';
            message.hidden = false;
        }
    }
    refresh();
    setInterval(refresh, 5000);
})();
