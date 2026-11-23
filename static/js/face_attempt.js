/*
 * Runs one admin face attempt (login or enrolment) against /api/admin/face/*:
 * starts it, shows the camera and the server's instruction, until it passes or
 * fails. On the kiosk the server reads the kiosk camera (MJPEG stream shown,
 * attempt polled). Remote (phone/PC through the tunnel) the server answers
 * `remote: true`: this browser opens its own camera and posts JPEG frames, each
 * answered with the attempt. Shared by admin_login.js and admin_faces.js.
 */
(function () {
    'use strict';

    const UI = window.UI;
    const POLL_MS = 200;  // fast enough for the enrolment 3-2-1 countdown
    const FRAME_GAP_MS = 100;  // remote: pause between posted frames
    const FRAME_WIDTH = 640;  // the server's face detector works at this size

    function sleep(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }

    // Remote camera: a <video> next to the (hidden) kiosk stream image.
    async function openCamera(els) {
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            throw new Error('Browser ini tidak bisa memakai kamera.');
        }
        let stream;
        try {
            stream = await navigator.mediaDevices.getUserMedia({
                video: { facingMode: 'user', width: { ideal: FRAME_WIDTH } }, audio: false,
            });
        } catch (e) {
            throw new Error('Izin kamera ditolak atau kamera tidak tersedia.');
        }
        const video = document.createElement('video');
        video.className = els.stream.className;
        video.muted = true;
        video.playsInline = true;
        video.setAttribute('playsinline', '');
        video.srcObject = stream;
        els.stream.hidden = true;
        els.stream.after(video);
        const label = els.live.querySelector('.camera-panel__label');
        const oldLabel = label ? label.textContent : null;
        if (label) label.textContent = 'Kamera perangkat ini';
        await video.play();
        return {
            video: video,
            canvas: document.createElement('canvas'),
            close: function () {
                stream.getTracks().forEach(function (t) { t.stop(); });
                video.remove();
                els.stream.hidden = false;
                if (label) label.textContent = oldLabel;
            },
        };
    }

    function grab(cam) {
        const w = cam.video.videoWidth, h = cam.video.videoHeight;
        if (!w || !h) return Promise.resolve(null);  // camera not ready yet
        const scale = Math.min(1, FRAME_WIDTH / w);
        cam.canvas.width = Math.round(w * scale);
        cam.canvas.height = Math.round(h * scale);
        cam.canvas.getContext('2d').drawImage(cam.video, 0, 0, cam.canvas.width, cam.canvas.height);
        return new Promise(function (r) { cam.canvas.toBlob(r, 'image/jpeg', 0.85); });
    }

    async function postFrame(blob) {
        try {
            const res = await fetch('/api/admin/face/frame', {
                method: 'POST',
                credentials: 'same-origin',
                headers: { 'X-CSRFToken': UI.getCSRFToken(), 'Content-Type': 'image/jpeg' },
                body: blob,
            });
            return await res.json();
        } catch (e) {
            return { success: false, error: 'Koneksi ke server terputus.' };
        }
    }

    // els: { live, stream, instruction, hint, error, cancel }; returns a promise
    // of the final attempt ({state: 'passed'|'failed', ...}) or null.
    async function run(startUrl, body, els) {
        els.error.textContent = '';
        const started = await UI.postJSON(startUrl, body);
        if (!started.success) {
            els.error.textContent = started.error || 'Tidak dapat memulai.';
            return null;
        }
        els.live.hidden = false;
        let cancelled = false;
        const onCancel = function () {
            cancelled = true;
            UI.postJSON('/api/admin/face/cancel', {});
        };
        els.cancel.addEventListener('click', onCancel);
        let cam = null;
        let a = started;
        try {
            if (a.remote) {
                try {
                    cam = await openCamera(els);
                } catch (e) {
                    UI.postJSON('/api/admin/face/cancel', {});
                    els.error.textContent = e.message;
                    return null;
                }
            } else {
                els.stream.src = '/camera/stream';
            }
            while (a.state === 'running' && !cancelled) {
                els.instruction.textContent = a.instruction;
                els.instruction.classList.toggle('face-login__instruction--count', !!a.countdown);
                els.hint.textContent = a.hint || '';
                let next;
                if (cam) {
                    await sleep(FRAME_GAP_MS);
                    const blob = await grab(cam);
                    next = blob ? await postFrame(blob) : await UI.fetchJSON('/api/admin/face/attempt');
                } else {
                    await sleep(POLL_MS);
                    next = await UI.fetchJSON('/api/admin/face/attempt');
                }
                if (!next.success) {
                    els.error.textContent = next.error || 'Percobaan berakhir.';
                    return null;
                }
                a = next;
            }
        } finally {
            els.cancel.removeEventListener('click', onCancel);
            if (cam) cam.close();
            els.stream.removeAttribute('src');  // closes the MJPEG connection
            els.live.hidden = true;
            els.instruction.classList.remove('face-login__instruction--count');
            els.hint.textContent = '';
        }
        if (cancelled) return null;
        if (a.state === 'failed') els.error.textContent = a.instruction;
        return a;
    }

    window.FaceAttempt = { run: run };
})();
