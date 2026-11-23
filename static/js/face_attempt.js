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
    const DeviceCamera = window.DeviceCamera;  // device_camera.js, loaded first
    const POLL_MS = 200;  // fast enough for the enrolment 3-2-1 countdown
    const FRAME_GAP_MS = 100;  // remote: pause between posted frames

    function sleep(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }

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
                    cam = await DeviceCamera.open(els);
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
                    const blob = await DeviceCamera.grab(cam);
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
