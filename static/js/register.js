/* Capture one fresh card on the server before creating or binding an account.
 * Self-registration also needs a face photo taken on the server from the
 * kiosk camera (guided 3-2-1 with reader beeps), when the camera is on. */
(function () {
    'use strict';
    const UI = window.UI;
    const CFG = window.REGISTER_CONFIG || {};
    const $ = function (id) { return document.getElementById(id); };
    const FIELDS = ['name', 'nim', 'email', 'phone'];
    let token = null;
    let ready = false;
    let timer = null;
    let expiresAt = 0;
    let generation = 0;
    let saving = false;
    // Face photo: required only when the server says the camera can take it.
    let photoRequired = false;
    let photoToken = null;
    let photoReady = false;
    let photoGen = 0;

    function updateSubmit() {
        $('form-submit').disabled = !ready || saving || (photoRequired && !photoReady);
    }

    function photoStatus(text, hint) {
        $('photo-status').textContent = text;
        $('photo-hint').textContent = hint || '';
    }

    function stopPhotoStream() {
        $('photo-stream').removeAttribute('src');  // closes the MJPEG connection
        $('photo-live').hidden = true;
    }

    async function pollPhoto(current) {
        while (current === photoGen) {
            await new Promise(function (r) { setTimeout(r, 200); });
            if (current !== photoGen) return;
            let res;
            try {
                res = await UI.fetchJSON('/api/register/photo?token=' + encodeURIComponent(photoToken));
            } catch (e) {
                continue;
            }
            if (current !== photoGen) return;
            if (!res.success) {
                stopPhotoStream();
                photoStatus(res.error || 'Foto gagal. Ulangi.');
                $('photo-start').disabled = false;
                return;
            }
            $('photo-count').textContent = res.countdown || '';
            if (res.state === 'running') {
                photoStatus(res.instruction, res.hint);
                continue;
            }
            stopPhotoStream();
            $('photo-start').disabled = false;
            $('photo-start').textContent = 'Ulangi foto';
            if (res.state === 'ready') {
                photoReady = true;
                $('photo-preview').src = '/api/register/photo/preview?token=' + encodeURIComponent(photoToken) + '&t=' + Date.now();
                $('photo-preview').hidden = false;
                photoStatus('Foto tersimpan. Ulangi kalau kurang jelas.');
            } else {
                photoStatus(res.instruction);
            }
            updateSubmit();
            return;
        }
    }

    async function startPhoto() {
        photoGen += 1;
        const current = photoGen;
        photoReady = false;
        updateSubmit();
        $('photo-start').disabled = true;
        $('photo-preview').hidden = true;
        $('form-error').textContent = '';
        let res;
        try {
            res = await UI.postJSON('/api/register/photo/start', {});
        } catch (e) {
            res = { success: false, error: 'Tidak dapat menghubungi server.' };
        }
        if (current !== photoGen) return;
        if (!res.success) {
            photoStatus(res.error || 'Kamera belum siap. Coba lagi.');
            $('photo-start').disabled = false;
            return;
        }
        photoToken = res.token;
        $('photo-live').hidden = false;
        $('photo-stream').src = '/camera/stream';
        photoStatus(res.instruction, res.hint);
        pollPhoto(current);
    }

    async function initPhoto() {
        if (CFG.student || !$('photo-field')) return;
        try {
            const res = await UI.fetchJSON('/api/register/photo/status');
            photoRequired = !!(res.success && res.available);
        } catch (e) {
            photoRequired = false;
        }
        $('photo-field').hidden = !photoRequired;
        updateSubmit();
    }

    function status(message) { $('nfc-status').textContent = message; }
    function fail(field, message) {
        $('form-error').textContent = message;
        if (field) {
            $(field).setAttribute('aria-invalid', 'true');
            $(field).focus();
        }
    }
    function resetCapture(message) {
        ready = false;
        token = null;
        generation += 1;
        clearTimeout(timer);
        updateSubmit();
        $('nfc-start').disabled = false;
        $('nfc-start').textContent = 'Baca kartu NFC';
        status(message);
    }
    async function pollCapture(current) {
        if (current !== generation) return;
        if (Date.now() >= expiresAt) {
            resetCapture('Waktu pembacaan habis. Tekan Baca kartu NFC, lalu tempelkan lagi.');
            return;
        }
        try {
            const res = await UI.fetchJSON('/api/nfc/registration');
            if (current !== generation) return;
            if (!res.success) {
                resetCapture(res.error || 'Pembacaan kartu berakhir. Silakan ulangi.');
                return;
            }
            ready = !!res.ready;
            updateSubmit();
            status(ready ? 'Kartu terbaca. Periksa data Anda, lalu simpan sebelum waktu pembacaan habis.'
                : res.connected ? 'Tempelkan kartu NFC ke pembaca. Angkat kembali setelah terbaca.'
                    : 'Pembaca NFC belum tersambung. Periksa perangkat; pembacaan akan dilanjutkan.');
        } catch (e) {
            ready = false;
            updateSubmit();
            status('Koneksi ke server terputus. Mencoba lagi…');
        }
        if (current === generation) timer = setTimeout(function () { pollCapture(current); }, 750);
    }
    async function startCapture() {
        resetCapture('Menyiapkan pembaca NFC…');
        const current = generation;
        $('nfc-start').disabled = true;
        $('form-error').textContent = '';
        try {
            const res = await UI.postJSON('/api/nfc/registration/start');
            if (current !== generation) return;
            if (!res.success || !res.token) {
                resetCapture(res.error || 'Pembaca belum siap. Coba lagi.');
                return;
            }
            token = res.token;
            expiresAt = Date.now() + 120000;
            $('nfc-start').disabled = false;
            $('nfc-start').textContent = 'Ulangi pembacaan';
            pollCapture(current);
        } catch (e) {
            resetCapture('Tidak dapat menghubungi server. Coba lagi.');
        }
    }
    function validate() {
        if (CFG.student) return true;
        for (let i = 0; i < FIELDS.length; i++) {
            const el = $(FIELDS[i]);
            if (!el.value.trim() || !el.checkValidity()) {
                fail(FIELDS[i], 'Periksa dan lengkapi ' + el.labels[0].textContent.toLowerCase() + '.');
                return false;
            }
        }
        if (!/^[A-Za-z0-9]{5,20}$/.test($('nim').value.trim())) {
            fail('nim', 'NIM berisi 5 sampai 20 huruf atau angka, tanpa spasi.');
            return false;
        }
        if (!/^[0-9+\-\s]{8,20}$/.test($('phone').value.trim())) {
            fail('phone', 'Nomor HP berisi 8 sampai 20 angka.');
            return false;
        }
        return true;
    }
    async function submit(ev) {
        ev.preventDefault();
        if (saving) return;
        $('form-error').textContent = '';
        if (!validate()) return;
        if (photoRequired && !photoReady) {
            fail(null, 'Ambil foto wajah terlebih dahulu.');
            $('photo-start').focus();
            return;
        }
        if (!ready || !token || Date.now() >= expiresAt) {
            resetCapture('Baca kartu NFC terlebih dahulu.');
            return;
        }
        saving = true;
        $('form-submit').disabled = true;
        $('nfc-start').disabled = true;
        clearTimeout(timer);
        const current = generation;
        try {
            let res;
            if (CFG.student) {
                res = await UI.postJSON('/api/admin/students/' + encodeURIComponent(CFG.student.student_id) + '/nfc', { nfc_token: token });
            } else {
                const data = new FormData();
                FIELDS.forEach(function (f) { data.append(f, $(f).value.trim()); });
                data.append('nfc_token', token);
                if (photoRequired) data.append('photo_token', photoToken);
                res = await UI.postForm('/api/register', data);
            }
            if (!res.success) {
                fail(null, res.error || 'Pendaftaran gagal. Coba lagi.');
                if (res.photo_missing) {
                    photoReady = false;
                    $('photo-preview').hidden = true;
                    photoStatus('Foto kedaluwarsa. Ambil foto lagi.');
                }
                return;
            }
            generation += 1;
            $('step-form').hidden = true;
            $('registration-done').hidden = false;
            $('registration-done').querySelector('a').focus();
        } catch (e) {
            fail(null, 'Tidak dapat menghubungi server. Periksa data pada admin sebelum mengulangi pendaftaran.');
        } finally {
            saving = false;
            if (current === generation) {
                $('nfc-start').disabled = false;
                pollCapture(current);
            }
        }
    }
    $('nfc-start').addEventListener('click', startCapture);
    if ($('photo-start')) $('photo-start').addEventListener('click', startPhoto);
    initPhoto();
    $('reg-form').addEventListener('submit', submit);
    FIELDS.forEach(function (f) {
        $(f).addEventListener('input', function () { $(f).removeAttribute('aria-invalid'); });
    });
    window.addEventListener('pagehide', function () {
        photoGen += 1;
        generation += 1;
        clearTimeout(timer);
        if (!token) return;
        fetch('/api/nfc/registration/cancel', {
            method: 'POST', credentials: 'same-origin', keepalive: true,
            headers: { 'X-CSRFToken': UI.getCSRFToken(), 'Content-Type': 'application/json' },
            body: JSON.stringify({ nfc_token: token }),
        }).catch(function () { /* Server capture also expires after 120 seconds. */ });
    });
})();
