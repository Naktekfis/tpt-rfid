/*
 * Shared helpers for pages on kiosk_base.html: CSRF, JSON fetch, toasts,
 * date formatting. Plain globals, no build step.
 */
(function () {
    'use strict';

    function getCSRFToken() {
        const meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.getAttribute('content') : '';
    }

    // fetch() that always resolves to {success, error, ...} (also for 429/500
    // HTML pages). Rejects only on network failure.
    async function fetchJSON(url, options) {
        const response = await fetch(url, Object.assign({ credentials: 'same-origin' }, options || {}));
        try {
            return await response.json();
        } catch (e) {
            if (response.status === 429) {
                return { success: false, error: 'Terlalu banyak percobaan. Tunggu sebentar lalu coba lagi.' };
            }
            return { success: false, error: 'Terjadi kesalahan server (HTTP ' + response.status + ')' };
        }
    }

    // POST with CSRF token and an optional JSON body.
    function postJSON(url, body) {
        const headers = { 'X-CSRFToken': getCSRFToken() };
        const options = { method: 'POST', headers: headers };
        if (body !== undefined) {
            headers['Content-Type'] = 'application/json';
            options.body = JSON.stringify(body);
        }
        return fetchJSON(url, options);
    }

    function toast(message, kind, ms) {
        const box = document.getElementById('toasts');
        if (!box) return;
        const el = document.createElement('div');
        el.className = 'toast' + (kind ? ' toast--' + kind : '');
        el.setAttribute('role', kind === 'danger' ? 'alert' : 'status');
        el.textContent = message;
        box.appendChild(el);
        setTimeout(function () { el.remove(); }, ms || 4000);
    }

    // Build an element: h('div', {class: 'x', text: 'y'}, child, ...)
    function h(tag, attrs) {
        const el = document.createElement(tag);
        const a = attrs || {};
        Object.keys(a).forEach(function (k) {
            const v = a[k];
            if (v === null || v === undefined || v === false) return;
            if (k === 'class') el.className = v;
            else if (k === 'text') el.textContent = v;
            else if (k.indexOf('on') === 0) el.addEventListener(k.slice(2), v);
            else el.setAttribute(k, v === true ? '' : v);
        });
        for (let i = 2; i < arguments.length; i++) {
            const c = arguments[i];
            if (c === null || c === undefined || c === false) continue;
            el.appendChild(typeof c === 'string' ? document.createTextNode(c) : c);
        }
        return el;
    }

    const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'Mei', 'Jun', 'Jul', 'Agu', 'Sep', 'Okt', 'Nov', 'Des'];

    // Backend sends WIB wall-clock times as naive ISO ("2026-10-18T14:05:00")
    // or HTTP-date ("Sun, 18 Oct 2026 14:05:00 GMT", also WIB despite "GMT").
    // Parse the digits instead of Date() so the browser time zone never matters.
    function parseWib(value) {
        if (!value) return null;
        let m = /(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/.exec(value);
        if (m) return { y: +m[1], mo: +m[2], d: +m[3], h: m[4], mi: m[5] };
        m = /(\d{1,2}) (\w{3}) (\d{4}) (\d{2}):(\d{2})/.exec(value);
        if (m) {
            const en = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
            return { y: +m[3], mo: en.indexOf(m[2]) + 1, d: +m[1], h: m[4], mi: m[5] };
        }
        return null;
    }

    function formatWibTime(value) {
        const t = parseWib(value);
        return t ? t.h + '.' + t.mi : '';
    }

    // "18 Okt 2026, 14.05"; short: "18 Okt, 14.05"
    function formatWibDate(value, short) {
        const t = parseWib(value);
        if (!t) return '';
        return t.d + ' ' + MONTHS[t.mo - 1] + (short ? '' : ' ' + t.y) + ', ' + t.h + '.' + t.mi;
    }

    window.UI = {
        getCSRFToken: getCSRFToken,
        fetchJSON: fetchJSON,
        postJSON: postJSON,
        toast: toast,
        h: h,
        parseWib: parseWib,
        formatWibTime: formatWibTime,
        formatWibDate: formatWibDate,
    };
})();
