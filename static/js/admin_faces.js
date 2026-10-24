/*
 * /admin/security: enrolled admin faces (enrol on the kiosk screen, delete)
 * and the admin login log (face, PIN, enrolment; photo when there is one).
 */
(function () {
    'use strict';

    const UI = window.UI;
    const h = UI.h;
    const $ = function (id) { return document.getElementById(id); };
    const METHODS = { face: 'Wajah', pin: 'PIN', enroll: 'Daftar wajah' };
    const REASONS = {
        spoof: 'tidak lolos cek keaslian', unknown_face: 'wajah tidak dikenali',
        timeout: 'waktu habis', face_lost: 'wajah hilang', camera: 'kamera',
        other_admin: 'wajah admin lain', wrong_pin: 'PIN salah', error: 'kesalahan',
    };

    async function remove(name, button) {
        if (!window.confirm('Hapus wajah ' + name + '? Admin ini tidak bisa login dengan wajah lagi.')) return;
        button.disabled = true;
        const res = await UI.postJSON('/api/admin/faces/delete', { name: name });
        UI.toast(res.success ? 'Wajah ' + name + ' dihapus.' : (res.error || 'Gagal menghapus.'), res.success ? 'ok' : 'danger');
        loadFaces();
    }

    async function loadFaces() {
        const res = await UI.fetchJSON('/api/admin/faces');
        const body = $('faces-body');
        body.textContent = '';
        if (!res.success) {
            body.appendChild(h('tr', null, h('td', { colspan: '4', class: 'empty', text: 'Data wajah admin belum dapat dimuat.' })));
            return;
        }
        $('enrol-form').hidden = !res.local;
        $('enrol-remote').hidden = res.local;
        const faces = res.faces || [];
        $('faces-count').textContent = faces.length ? faces.length + ' admin' : '';
        if (!faces.length) {
            body.appendChild(h('tr', null, h('td', { colspan: '4', class: 'empty', text: 'Belum ada wajah admin terdaftar.' })));
            return;
        }
        faces.forEach(function (f) {
            const del = h('button', { type: 'button', class: 'linkbtn linkbtn--danger', text: 'Hapus' });
            del.addEventListener('click', function () { remove(f.name, del); });
            body.appendChild(h('tr', null,
                h('td', null, h('strong', { text: f.name })),
                h('td', { class: 'num', text: String(f.samples) }),
                h('td', { class: 'num', text: UI.formatWibDate(f.created_at) }),
                h('td', { class: 'actions' }, del)));
        });
    }

    async function loadLogins() {
        const res = await UI.fetchJSON('/api/admin/login_events');
        const body = $('logins-body');
        body.textContent = '';
        const events = res.success ? res.events || [] : [];
        if (!events.length) {
            body.appendChild(h('tr', null, h('td', { colspan: '5', class: 'empty',
                text: res.success ? 'Belum ada percobaan login.' : 'Riwayat login belum dapat dimuat.' })));
            return;
        }
        events.forEach(function (e) {
            const result = e.success
                ? h('span', { class: 'status status--brand', text: 'Berhasil' })
                : h('span', { class: 'status status--danger', text: 'Gagal' + (e.reason ? ' · ' + (REASONS[e.reason] || e.reason) : '') });
            const photo = e.has_photo
                ? h('a', { href: '/api/admin/login_events/' + e.event_id + '/photo', target: '_blank', rel: 'noopener', text: 'Lihat foto' })
                : h('span', { class: 'muted', text: '—' });
            body.appendChild(h('tr', null,
                h('td', { class: 'num', text: UI.formatWibDate(e.at) }),
                h('td', { text: METHODS[e.method] || e.method }),
                h('td', null, result),
                h('td', { text: e.admin_name || '—' }),
                h('td', null, photo)));
        });
    }

    $('enrol-form').addEventListener('submit', async function (ev) {
        ev.preventDefault();
        const name = $('enrol-name').value.trim();
        if (!name) { $('enrol-name').focus(); return; }
        $('enrol-form').hidden = true;
        const a = await window.FaceAttempt.run('/api/admin/faces/enroll/start', { name: name }, {
            live: $('enrol-live'),
            stream: $('enrol-stream'),
            instruction: $('enrol-instruction'),
            hint: $('enrol-hint'),
            error: $('enrol-error'),
            cancel: $('enrol-cancel'),
        });
        $('enrol-form').hidden = false;
        if (a && a.state === 'passed') {
            UI.toast('Wajah ' + name + ' terdaftar.', 'ok');
            $('enrol-name').value = '';
        }
        loadFaces();
        loadLogins();
    });

    loadFaces();
    loadLogins();
    setInterval(loadLogins, 10000);
})();
