/*
 * Runs one admin face attempt (login or enrolment) against /api/admin/face/*:
 * starts it, shows the kiosk camera stream and the server's instruction, polls
 * until it passes or fails. Shared by admin_login.js and admin_faces.js.
 */
(function () {
    'use strict';

    const UI = window.UI;
    const POLL_MS = 200;  // fast enough for the enrolment 3-2-1 countdown

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
        els.stream.src = '/camera/stream';
        let cancelled = false;
        const onCancel = function () {
            cancelled = true;
            UI.postJSON('/api/admin/face/cancel', {});
        };
        els.cancel.addEventListener('click', onCancel);
        let a = started;
        try {
            while (a.state === 'running' && !cancelled) {
                els.instruction.textContent = a.instruction;
                els.instruction.classList.toggle('face-login__instruction--count', !!a.countdown);
                els.hint.textContent = a.hint || '';
                await new Promise(function (r) { setTimeout(r, POLL_MS); });
                const next = await UI.fetchJSON('/api/admin/face/attempt');
                if (!next.success) {
                    els.error.textContent = next.error || 'Percobaan berakhir.';
                    return null;
                }
                a = next;
            }
        } finally {
            els.cancel.removeEventListener('click', onCancel);
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
