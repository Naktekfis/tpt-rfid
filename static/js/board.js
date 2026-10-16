/*
 * Tool board helpers shared by /monitor and the admin pages: tool photo tile
 * with initials fallback, unit status marks and their legend. Same marks as
 * the kiosk (ui.css .unit-mark).
 */
(function () {
    'use strict';

    const h = window.UI.h;

    // Unit mark kinds, in legend order.
    const MARKS = [
        ['present', 'di rak'],
        ['borrowed', 'dipinjam'],
        ['overdue', 'terlambat'],
        ['missing', 'hilang'],
        ['unknown', 'belum terbaca'],
    ];

    function initials(name) {
        const words = String(name || '').trim().split(/\s+/).filter(Boolean);
        if (!words.length) return '';
        if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
        return (words[0][0] + words[1][0]).toUpperCase();
    }

    function toolPhoto(url, name, size) {
        const tile = h('div', { class: 'tool-photo tool-photo--' + size });
        const fallback = function () {
            tile.textContent = '';
            tile.appendChild(h('span', { class: 'tool-photo__initials', 'aria-hidden': 'true', text: initials(name) }));
        };
        if (url) {
            const img = h('img', { src: url, alt: 'Foto ' + name, loading: 'lazy' });
            img.onerror = fallback;
            tile.appendChild(img);
        } else {
            fallback();
        }
        return tile;
    }

    function markOf(u) {
        if (u.status === 'borrowed') return u.is_overdue ? 'overdue' : 'borrowed';
        if (u.status === 'available') {
            if (u.presence === 'present') return 'present';
            if (u.presence === 'missing') return 'missing';
        }
        return 'unknown';
    }

    function labelOf(kind) {
        const m = MARKS.filter(function (x) { return x[0] === kind; })[0];
        return m ? m[1] : kind;
    }

    function unitsEl(units) {
        const row = h('div', { class: 'units' });
        units.forEach(function (u) {
            const kind = markOf(u);
            let title = u.name + ': ' + labelOf(kind);
            if (u.borrower_name) title += ' (' + u.borrower_name + ')';
            row.appendChild(h('span', { class: 'unit-mark unit-mark--' + kind, title: title }));
        });
        return row;
    }

    function legendEl(used) {
        const box = h('div', { class: 'legend' });
        MARKS.forEach(function (m) {
            if (m[0] !== 'present' && used && !used[m[0]]) return;
            box.appendChild(h('span', { class: 'legend__item' },
                h('span', { class: 'unit-mark unit-mark--' + m[0], 'aria-hidden': 'true' }), m[1]));
        });
        return box;
    }

    window.Board = {
        MARKS: MARKS,
        initials: initials,
        toolPhoto: toolPhoto,
        markOf: markOf,
        labelOf: labelOf,
        unitsEl: unitsEl,
        legendEl: legendEl,
    };
})();
