/*
 * /monitor (public, read-only): the kiosk board from /api/kiosk/state,
 * polled every second. Per tool type: photo, unit marks, and one line per unit
 * that is not on the rack (borrower + due date, overdue in amber, missing in red).
 */
(function () {
    'use strict';

    const UI = window.UI;
    const B = window.Board;
    const h = UI.h;
    const POLL_MS = 500;

    const $ = function (id) { return document.getElementById(id); };
    let lastKey = '';
    let loaded = false;
    let serverDown = false;

    function loanLine(u) {
        const kind = B.markOf(u);
        if (kind === 'borrowed' || kind === 'overdue') {
            const who = (u.borrower_name || '-') + (u.borrower_nim ? ' (' + u.borrower_nim + ')' : '');
            return h('li', { class: kind === 'overdue' ? 'is-overdue' : '' },
                h('span', { text: u.name }),
                h('span', { text: who }),
                h('span', { text: (kind === 'overdue' ? 'terlambat, batas ' : 'batas ') + UI.formatWibDate(u.due_at, true) }));
        }
        if (kind === 'missing') {
            return h('li', { class: 'is-missing' },
                h('span', { text: u.name }), h('span', { text: 'tidak ada di rak, belum tercatat dipinjam' }), h('span'));
        }
        return null;
    }

    function render(board, alarms) {
        const key = JSON.stringify([board, alarms]);
        if (key === lastKey) return;
        lastKey = key;

        const list = $('board');
        list.textContent = '';
        const used = {};
        let present = 0;
        let total = 0;
        if (!board.length) list.appendChild(h('li', { class: 'empty board__type', text: 'Belum ada alat terdaftar.' }));
        board.forEach(function (g) {
            const kinds = g.units.map(B.markOf);
            kinds.forEach(function (k) { used[k] = true; });
            const n = function (k) { return kinds.filter(function (x) { return x === k; }).length; };
            present += n('present');
            total += kinds.length;
            let count = n('present') + ' dari ' + kinds.length + ' di rak';
            let cls = 'board__count';
            if (n('overdue')) { count += ' · ' + n('overdue') + ' terlambat'; cls += ' board__count--warn'; }
            if (n('missing')) { count += ' · ' + n('missing') + ' hilang'; cls = 'board__count board__count--danger'; }

            const loans = h('ul', { class: 'board__loans' });
            g.units.forEach(function (u) {
                const line = loanLine(u);
                if (line) loans.appendChild(line);
            });
            list.appendChild(h('li', { class: 'board__type' },
                B.toolPhoto(g.photo_url, g.type_name, 'sm'),
                h('div', { class: 'board__body' },
                    h('div', { class: 'board__title' },
                        h('h2', { text: g.type_name }),
                        h('span', { class: cls, text: count })),
                    B.unitsEl(g.units),
                    loans.childElementCount ? loans : null)));
        });
        $('board-meta').textContent = present + ' dari ' + total + ' unit di rak';
        const legend = $('board-legend');
        legend.textContent = '';
        legend.appendChild(B.legendEl(used));

        const banners = $('banners');
        banners.textContent = '';
        if (alarms.length) {
            banners.appendChild(h('div', { class: 'bar bar--danger', role: 'alert' },
                'Alarm: ' + alarms.map(function (a) { return a.tool_name; }).join(', ') +
                ' diambil tanpa sesi KTM.'));
        }
    }

    async function poll() {
        try {
            const s = await UI.fetchJSON('/api/kiosk/state');
            if (!s.success) throw new Error('State unavailable');
            loaded = true;
            serverDown = false;
            render(s.board || [], s.alarms || []);
        } catch (e) {
            if (!loaded) {
                $('board').textContent = '';
                $('board').appendChild(h('li', { class: 'empty board__type', text: 'Data alat belum tersedia. Mencoba kembali otomatis…' }));
            }
            if (!serverDown) {
                serverDown = true;
                $('banners').textContent = '';
                $('banners').appendChild(h('div', { class: 'bar bar--danger', role: 'alert' },
                    'Koneksi ke server terputus. Data di layar mungkin tidak terbaru.'));
                lastKey = '';
            }
        }
        setTimeout(poll, POLL_MS);
    }

    poll();
})();
