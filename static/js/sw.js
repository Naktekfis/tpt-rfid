/*
 * Service worker for the installable admin app (PWA). It caches nothing:
 * admin data must always be live. It only exists so browsers offer
 * "Install", and shows a short message instead of the browser's error page
 * when the Jetson cannot be reached. Browsers run it only on https or
 * localhost.
 */
'use strict';

const OFFLINE = '<!doctype html><html lang="id"><meta charset="utf-8">' +
    '<meta name="viewport" content="width=device-width, initial-scale=1">' +
    '<title>Admin Lab tidak terhubung</title>' +
    '<body style="font-family:system-ui,sans-serif;max-width:32rem;margin:15vh auto;padding:0 16px;color:#1d2731">' +
    '<h1 style="font-size:1.4rem">Tidak terhubung ke kiosk</h1>' +
    '<p>Pastikan perangkat ini ada di jaringan lab dan kiosk menyala, lalu muat ulang.</p>' +
    '<button onclick="location.reload()" style="font:inherit;padding:.5rem 1rem">Muat ulang</button></body></html>';

self.addEventListener('install', function () { self.skipWaiting(); });
self.addEventListener('activate', function (event) { event.waitUntil(self.clients.claim()); });

self.addEventListener('fetch', function (event) {
    if (event.request.mode !== 'navigate') return;
    event.respondWith(fetch(event.request).catch(function () {
        return new Response(OFFLINE, { headers: { 'Content-Type': 'text/html; charset=utf-8' } });
    }));
});
