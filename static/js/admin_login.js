/*
 * /admin/login: "Masuk dengan wajah" on the kiosk screen when face login is
 * available; the PIN form below always works.
 */
(function () {
    'use strict';

    const UI = window.UI;
    const $ = function (id) { return document.getElementById(id); };

    async function init() {
        const status = await UI.fetchJSON('/api/admin/face/status');
        if (!status.success || !status.available || !status.local) return;
        $('face-login').hidden = false;
        const start = $('face-start');
        start.addEventListener('click', async function () {
            start.hidden = true;
            const a = await window.FaceAttempt.run('/api/admin/face/login/start', {}, {
                live: $('face-live'),
                stream: $('face-stream'),
                instruction: $('face-instruction'),
                hint: $('face-hint'),
                error: $('face-error'),
                cancel: $('face-cancel'),
            });
            if (a && a.state === 'passed') {
                window.location.href = '/admin';
                return;
            }
            start.hidden = false;
            start.textContent = 'Coba lagi dengan wajah';
            if (a) $('pin').focus();
        });
    }

    init();
})();
