/*
 * This browser's own camera (phone/PC through the tunnel): a <video> placed
 * next to the (hidden) kiosk stream image, and one JPEG grab at a time.
 * Shared by face_attempt.js (remote face login) and register.js (remote
 * admin registration photo).
 */
(function () {
    'use strict';

    const FRAME_WIDTH = 640;  // the server's face detector works at this size

    // els: { live, stream }; resolves to { video, canvas, close }.
    async function open(els) {
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

    // One JPEG (at most FRAME_WIDTH wide), or null while the camera warms up.
    function grab(cam) {
        const w = cam.video.videoWidth, h = cam.video.videoHeight;
        if (!w || !h) return Promise.resolve(null);  // camera not ready yet
        const scale = Math.min(1, FRAME_WIDTH / w);
        cam.canvas.width = Math.round(w * scale);
        cam.canvas.height = Math.round(h * scale);
        cam.canvas.getContext('2d').drawImage(cam.video, 0, 0, cam.canvas.width, cam.canvas.height);
        return new Promise(function (r) { cam.canvas.toBlob(r, 'image/jpeg', 0.85); });
    }

    window.DeviceCamera = { open: open, grab: grab };
})();
