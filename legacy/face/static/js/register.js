/*
 * /daftar: step 1 posts the form to /api/register, step 2 records the face
 * with POST /api/face/enroll/<student_id> (the server captures ~8 frames over
 * ~2 s). The created student is kept in sessionStorage, so a failed capture
 * or a page reload retries on the same student without the form.
 * Admin mode (/daftar?student_id=<id> with an admin session) starts at step 2.
 */
(function () {
    'use strict';

    const UI = window.UI;
    const h = UI.h;
    const CFG = window.REGISTER_CONFIG || {};
    const STORE = 'tpt-register-student';
    const CAMERA_RETRY_MS = 8000;

    const $ = function (id) { return document.getElementById(id); };

    let student = CFG.student || null;

    // ---------- Step switching ----------

    function showForm() {
        $('step-face').hidden = true;
        $('step-form').hidden = false;
        $('name').focus();
    }

    function showFace() {
        $('step-form').hidden = true;
        $('step-face').hidden = false;
        $('face-who').textContent = student.name + ' (' + student.nim + ')';
        $('face-result').hidden = true;
        $('face-intro').hidden = false;
        $('face-actions').hidden = false;
        $('face-btn').textContent = 'Rekam wajah';
        startCamera();
        $('face-btn').focus();
    }

    function remember(s) {
        try {
            if (s) sessionStorage.setItem(STORE, JSON.stringify(s));
            else sessionStorage.removeItem(STORE);
        } catch (e) { /* private mode: retry still works until reload */ }
    }

    function recalled() {
        try {
            const raw = sessionStorage.getItem(STORE);
            return raw ? JSON.parse(raw) : null;
        } catch (e) {
            return null;
        }
    }

    // ---------- Step 1: form ----------

    const FIELDS = ['name', 'nim', 'email', 'phone'];

    function clearErrors() {
        $('form-error').textContent = '';
        FIELDS.forEach(function (f) { $(f).removeAttribute('aria-invalid'); });
    }

    function fail(field, message) {
        $('form-error').textContent = message;
        if (field) {
            $(field).setAttribute('aria-invalid', 'true');
            $(field).focus();
        }
    }

    // Field order, so the first problem is the one nearest the top.
    const CHECKS = [
        ['name', function (v) { return v ? '' : 'Isi nama lengkap Anda.'; }],
        ['nim', function (v) {
            if (!v) return 'Isi NIM Anda.';
            return /^[A-Za-z0-9]{5,20}$/.test(v) ? '' : 'NIM berisi 5 sampai 20 huruf atau angka, tanpa spasi.';
        }],
        ['email', function (v, el) {
            if (!v) return 'Isi alamat email Anda.';
            return el.checkValidity() ? '' : 'Alamat email belum benar.';
        }],
        ['phone', function (v) {
            if (!v) return 'Isi nomor HP Anda.';
            return /^[0-9+\-\s]{8,20}$/.test(v) ? '' : 'Nomor HP berisi 8 sampai 20 angka.';
        }],
    ];

    function validate() {
        for (let i = 0; i < CHECKS.length; i++) {
            const el = $(CHECKS[i][0]);
            const msg = CHECKS[i][1](el.value.trim(), el);
            if (msg) {
                fail(CHECKS[i][0], msg);
                return false;
            }
        }
        if (!$('consent').checked) {
            fail(null, 'Centang persetujuan penyimpanan foto wajah untuk melanjutkan.');
            $('consent').focus();
            return false;
        }
        return true;
    }

    async function submitForm(ev) {
        ev.preventDefault();
        clearErrors();
        if (!validate()) return;
        const btn = $('form-submit');
        btn.disabled = true;
        const fd = new FormData();
        FIELDS.forEach(function (f) { fd.append(f, $(f).value.trim()); });
        try {
            const res = await UI.postForm('/api/register', fd);
            if (!res.success) {
                if (res.error === 'NIM sudah terdaftar') {
                    fail('nim', 'NIM ini sudah terdaftar. Bila Anda belum merekam wajah, hubungi admin.');
                } else if (res.error === 'Format NIM tidak valid') {
                    fail('nim', 'NIM berisi 5 sampai 20 huruf atau angka, tanpa spasi.');
                } else {
                    fail(null, res.error || 'Pendaftaran gagal. Coba lagi.');
                }
                return;
            }
            student = res.student;
            remember(student);
            showFace();
        } catch (e) {
            fail(null, 'Tidak dapat menghubungi server. Coba lagi.');
        } finally {
            btn.disabled = false;
        }
    }

    // ---------- Step 2: camera ----------

    let cameraStarted = false;

    function startCamera() {
        if (cameraStarted) return;
        cameraStarted = true;
        const img = $('cam-img');
        const label = $('cam-label');
        img.onload = function () {
            label.hidden = true;
            img.hidden = false;
        };
        img.onerror = function () {
            img.hidden = true;
            label.hidden = false;
            label.textContent = 'Kamera tidak tersedia';
            setTimeout(function () { img.src = CFG.cameraStream + '?t=' + Date.now(); }, CAMERA_RETRY_MS);
        };
        img.src = CFG.cameraStream;
    }

    // ---------- Step 2: enroll ----------

    const HINTS = {
        no_face: 'Pastikan seluruh wajah berada di dalam bingkai.',
        multiple_faces: 'Pastikan hanya Anda yang terlihat di kamera.',
        too_small: 'Mendekatlah ke kamera sampai wajah mengisi bingkai.',
        blurry: 'Gerakkan kepala lebih pelan dan pastikan cahaya cukup.',
    };

    function result(kind, title, paragraphs, actions, list) {
        const box = $('face-result');
        box.className = 'result result--' + kind;
        box.textContent = '';
        box.appendChild(h('h2', { text: title }));
        (paragraphs || []).forEach(function (p) { box.appendChild(h('p', { text: p })); });
        if (list && list.length) {
            const ul = h('ul');
            list.forEach(function (t) { ul.appendChild(h('li', { text: t })); });
            box.appendChild(ul);
        }
        if (actions && actions.length) {
            const row = h('div', { class: 'form__actions' });
            actions.forEach(function (a) { row.appendChild(a); });
            box.appendChild(row);
        }
        box.hidden = false;
    }

    function link(href, text, primary) {
        return h('a', { class: 'btn ' + (primary ? 'btn--primary' : 'btn--secondary'), href: href, text: text });
    }

    function backLink(primary) {
        return CFG.adminMode
            ? link(CFG.adminMonitorUrl, 'Kembali ke Monitor', primary)
            : link(CFG.kioskUrl, 'Ke kiosk', primary);
    }

    // Final outcome: no more recording on this page.
    function finish(kind, title, paragraphs, actions) {
        $('face-intro').hidden = true;
        $('face-actions').hidden = true;
        $('face-restart').hidden = true;
        result(kind, title, paragraphs, actions);
        const first = $('face-result').querySelector('a, button');
        if (first) first.focus();
    }

    // Retryable outcome: instructions stay, the button becomes "Coba lagi".
    function again(kind, title, paragraphs, list) {
        $('face-btn').textContent = 'Coba lagi';
        result(kind, title, paragraphs, null, list);
        $('face-btn').focus();
    }

    function showResult(status, res, httpOk) {
        if (status === 'ok') {
            $('cam').classList.add('camera-panel--done');
            remember(null);
            const paras = CFG.adminMode
                ? ['Wajah ' + student.name + ' sudah direkam ulang dan dapat dipakai di kiosk.']
                : ['Silakan kembali ke kiosk. Di sana, lihat ke kamera untuk meminjam atau mengembalikan alat.'];
            if (res && res.verified === false) {
                paras.push('Uji pengenalan setelah perekaman belum berhasil. Bila nanti wajah tidak dikenali di kiosk, minta admin merekam ulang.');
            }
            finish('ok', CFG.adminMode ? 'Wajah tersimpan.' : 'Pendaftaran selesai.', paras, [backLink(true)]);
            return;
        }
        if (status === 'insufficient') {
            const problems = (res && res.problems) || {};
            const hints = Object.keys(HINTS).filter(function (k) { return problems[k]; }).map(function (k) { return HINTS[k]; });
            if (!hints.length) hints.push(HINTS.no_face, HINTS.blurry);
            again('warn', 'Wajah belum terekam dengan baik',
                ['Hanya ' + (res.good_frames || 0) + ' dari ' + (res.needed || 3) + ' gambar yang dibutuhkan cukup jelas.'],
                hints);
            return;
        }
        if (status === 'duplicate') {
            remember(null);
            finish('danger', 'Wajah sudah terdaftar',
                ['Wajah ini sudah terdaftar atas nama mahasiswa lain. Hubungi admin.'],
                [CFG.adminMode ? backLink(false) : link(CFG.menuUrl, 'Kembali ke menu', false)]);
            return;
        }
        if (status === 'already_enrolled') {
            remember(null);
            finish('warn', 'Wajah sudah terekam',
                ['Wajah untuk akun ini sudah terdaftar. Untuk merekam ulang, hubungi admin.'],
                [backLink(false)]);
            return;
        }
        if (status === 'not_found') {
            remember(null);
            finish('danger', 'Data tidak ditemukan',
                CFG.adminMode ? ['Data mahasiswa ini tidak ditemukan.'] : ['Data pendaftaran Anda tidak ditemukan. Silakan isi formulir lagi.'],
                [CFG.adminMode ? backLink(false)
                    : h('button', { type: 'button', class: 'btn btn--primary', onclick: restart, text: 'Isi formulir lagi' })]);
            return;
        }
        if (status === 'no_camera') {
            again('warn', 'Kamera tidak mengirim gambar',
                ['Periksa apakah kamera tersambung, lalu coba lagi.' + (CFG.adminMode ? '' : ' Data diri Anda sudah tersimpan.')]);
            return;
        }
        if (status === 'models_missing') {
            again('danger', 'Pengenalan wajah belum siap',
                ['Model pengenalan wajah belum terpasang di perangkat ini. Hubungi admin.' +
                    (CFG.adminMode ? '' : ' Data diri Anda sudah tersimpan; perekaman dapat diulang nanti.')]);
            return;
        }
        again('danger', 'Perekaman gagal',
            [(res && res.error) || ((httpOk ? 'Terjadi kesalahan.' : 'Tidak dapat menghubungi server.') + ' Coba lagi.')]);
    }

    async function enroll() {
        if (!student) return;
        const btn = $('face-btn');
        const panel = $('cam');
        btn.disabled = true;
        $('face-busy').hidden = false;
        $('face-result').hidden = true;
        panel.classList.add('camera-panel--busy');
        panel.classList.remove('camera-panel--done');
        try {
            const res = await UI.postJSON('/api/face/enroll/' + encodeURIComponent(student.student_id));
            showResult(res.status, res, true);
        } catch (e) {
            showResult('network', null, false);
        } finally {
            btn.disabled = false;
            $('face-busy').hidden = true;
            panel.classList.remove('camera-panel--busy');
        }
    }

    function restart() {
        student = null;
        $('face-restart').hidden = true;
        remember(null);
        $('reg-form').reset();
        showForm();
    }

    // ---------- Init ----------

    $('reg-form').addEventListener('submit', submitForm);
    FIELDS.forEach(function (f) {
        $(f).addEventListener('input', function () { $(f).removeAttribute('aria-invalid'); });
    });
    $('face-btn').addEventListener('click', enroll);

    $('face-restart-btn').addEventListener('click', restart);

    if (!student && !CFG.adminMode) {
        student = recalled();
        // Someone else's unfinished registration on this kiosk browser.
        if (student) $('face-restart').hidden = false;
    }
    if (student) showFace();
})();
