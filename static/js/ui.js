/*
 * Shared helpers for pages on kiosk_base.html / app_base.html: CSRF, JSON
 * fetch, toasts, date formatting, clock. Plain globals, no build step.
 */
(function () {
    'use strict';

    function getCSRFToken() {
        const meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.getAttribute('content') : '';
    }

    // fetch() that always resolves to {success, error, ...} (also for 429/500
    // HTML pages). GETs also reject after 5 s so a stalled poll can recover.
    async function fetchJSON(url, options) {
        const request = Object.assign({ credentials: 'same-origin' }, options || {});
        async function readJSON() {
            const response = await fetch(url, request);
            try {
                return await response.json();
            } catch (e) {
                if (response.status === 429) {
                    return { success: false, error: 'Terlalu banyak percobaan. Tunggu sebentar lalu coba lagi.' };
                }
                return { success: false, error: 'Terjadi kesalahan server (HTTP ' + response.status + ')' };
            }
        }
        // Mutations may legitimately take longer and must never be retried here.
        if ((request.method || 'GET').toUpperCase() !== 'GET') return readJSON();
        const callerSignal = request.signal;
        const controller = new AbortController();
        request.signal = controller.signal;
        let timer;
        let onAbort;
        const deadline = new Promise(function (resolve, reject) {
            function cancel(name, message) {
                const error = new Error(message);
                error.name = name;
                reject(error);
                controller.abort();
            }
            onAbort = function () { cancel('AbortError', 'Request cancelled'); };
            timer = setTimeout(function () { cancel('TimeoutError', 'Request timed out'); }, 5000);
            if (callerSignal) {
                callerSignal.addEventListener('abort', onAbort, { once: true });
                if (callerSignal.aborted) onAbort();
            }
        });
        try {
            return await Promise.race([deadline, readJSON()]);
        } finally {
            clearTimeout(timer);
            if (callerSignal) callerSignal.removeEventListener('abort', onAbort);
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

    const DAYS = ['Minggu', 'Senin', 'Selasa', 'Rabu', 'Kamis', 'Jumat', 'Sabtu'];
    const MONTHS_LONG = ['Januari', 'Februari', 'Maret', 'April', 'Mei', 'Juni', 'Juli', 'Agustus',
        'September', 'Oktober', 'November', 'Desember'];

    // "Minggu 18 Oktober, 14.05" (weekday from the WIB date itself).
    function formatWibDay(value) {
        const t = parseWib(value);
        if (!t) return '';
        const wd = new Date(Date.UTC(t.y, t.mo - 1, t.d)).getUTCDay();
        return DAYS[wd] + ' ' + t.d + ' ' + MONTHS_LONG[t.mo - 1] + ', ' + t.h + '.' + t.mi;
    }

    // Live WIB clock in every [data-clock] element ("14.05").
    function startClock() {
        const fmt = new Intl.DateTimeFormat('id-ID', {
            timeZone: 'Asia/Jakarta', hour: '2-digit', minute: '2-digit', hour12: false,
        });
        function tick() {
            const text = fmt.format(new Date()).replace(':', '.');
            document.querySelectorAll('[data-clock]').forEach(function (el) {
                if (el.textContent !== text) el.textContent = text;
            });
        }
        tick();
        setInterval(tick, 5000);
    }

    // POST a FormData (multipart) with the CSRF token.
    function postForm(url, formData) {
        return fetchJSON(url, {
            method: 'POST',
            headers: { 'X-CSRFToken': getCSRFToken() },
            body: formData,
        });
    }

    // Persistent, deduplicated feedback for data that may be stale.
    function loadNotice(id, message, retry) {
        const box = document.getElementById(id);
        if (!box) return;
        box.hidden = !message;
        if (box.dataset.message === message) return;
        box.dataset.message = message;
        box.textContent = '';
        if (!message) return;
        box.appendChild(h('span', { text: message }));
        if (retry) {
            const button = h('button', { type: 'button', class: 'btn btn--secondary btn--sm', text: 'Coba lagi' });
            button.addEventListener('click', async function () {
                button.disabled = true;
                button.textContent = 'Memuat…';
                try { await retry(); }
                finally { button.disabled = false; button.textContent = 'Coba lagi'; }
            });
            box.appendChild(button);
        }
    }

    document.addEventListener('DOMContentLoaded', function () {
        document.querySelectorAll('.page .table').forEach(function (table) {
            const section = table.closest('.section');
            const heading = (section && section.querySelector('h2')) || document.querySelector('.page h1');
            const wrapper = h('div', {
                class: 'table-scroll', tabindex: '0', role: 'region',
                'aria-label': (heading ? heading.textContent : 'Tabel data') + '. Geser ke samping untuk melihat seluruh kolom.',
            });
            table.before(wrapper);
            wrapper.appendChild(table);
        });
    });

    // ---------- Row menu ("Kelola ▾") ----------
    // One button per table row; it opens a small menu of labelled actions
    // ({label, desc, danger, onSelect}). The menu lives in <body>, so table
    // scrolling or a row re-render does not clip or close it.
    let openMenu = null;

    function closeMenu(refocus) {
        if (!openMenu) return;
        const m = openMenu;
        openMenu = null;
        m.el.remove();
        m.button.setAttribute('aria-expanded', 'false');
        if (refocus && m.button.isConnected) m.button.focus();
    }

    // Below the button (above when there is no room), right edges aligned.
    function placeMenu() {
        if (!openMenu) return;
        const el = openMenu.el;
        if (!openMenu.button.isConnected) { closeMenu(false); return; }
        const r = openMenu.button.getBoundingClientRect();
        const left = Math.max(8, Math.min(r.right - el.offsetWidth, window.innerWidth - el.offsetWidth - 8));
        const below = r.bottom + 4 + el.offsetHeight <= window.innerHeight;
        el.style.left = (left + window.scrollX) + 'px';
        el.style.top = ((below ? r.bottom + 4 : r.top - 4 - el.offsetHeight) + window.scrollY) + 'px';
    }

    function rowMenu(label, items) {
        const button = h('button', { type: 'button', class: 'btn btn--secondary btn--sm rowmenu__button',
            'aria-haspopup': 'menu', 'aria-expanded': 'false' }, label + ' ',
            h('span', { class: 'rowmenu__caret', 'aria-hidden': 'true', text: '▾' }));
        button.addEventListener('click', function (event) {
            event.stopPropagation();
            const wasOpen = openMenu && openMenu.button === button;
            closeMenu(false);
            if (wasOpen) return;
            const el = h('ul', { class: 'rowmenu', role: 'menu' });
            items.filter(Boolean).forEach(function (item) {
                const choice = h('button', { type: 'button', role: 'menuitem',
                    class: 'rowmenu__item' + (item.danger ? ' rowmenu__item--danger' : '') },
                    h('span', { class: 'rowmenu__label', text: item.label }),
                    item.desc ? h('span', { class: 'rowmenu__desc', text: item.desc }) : null);
                choice.addEventListener('click', function () {
                    closeMenu(false);
                    item.onSelect();
                });
                el.appendChild(h('li', { role: 'none', class: item.separate ? 'rowmenu__sep' : null }, choice));
            });
            document.body.appendChild(el);
            button.setAttribute('aria-expanded', 'true');
            openMenu = { el: el, button: button };
            placeMenu();
            el.querySelector('button').focus({ preventScroll: true });
        });
        return button;
    }

    document.addEventListener('click', function (event) {
        if (openMenu && !openMenu.el.contains(event.target)) closeMenu(false);
    });
    document.addEventListener('keydown', function (event) {
        if (!openMenu) return;
        if (event.key === 'Escape') closeMenu(true);
        if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
            const items = Array.prototype.slice.call(openMenu.el.querySelectorAll('button'));
            const i = items.indexOf(document.activeElement);
            const next = event.key === 'ArrowDown' ? i + 1 : i - 1;
            items[(next + items.length) % items.length].focus();
            event.preventDefault();
        }
    });
    window.addEventListener('resize', placeMenu);
    window.addEventListener('scroll', placeMenu, true);

    window.UI = {
        rowMenu: rowMenu,
        loadNotice: loadNotice,
        getCSRFToken: getCSRFToken,
        postForm: postForm,
        startClock: startClock,
        fetchJSON: fetchJSON,
        postJSON: postJSON,
        toast: toast,
        h: h,
        parseWib: parseWib,
        formatWibTime: formatWibTime,
        formatWibDate: formatWibDate,
        formatWibDay: formatWibDay,
    };
})();
