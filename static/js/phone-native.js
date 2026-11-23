/*
 * Phone variants B and C (?variant=b|c, set on <html data-variant> by app_base.html), phone width only:
 *  - segmented panes: every [data-pane="Label"] plus the siblings after it, up to the next marker, is one pane
 *    (data-pane-count="id" mirrors that element's last number into the tab);
 *  - a filter bottom sheet: the [data-sheet] nodes move into a <dialog> while it is open and back afterwards.
 * Built once, undone when the media query stops matching. The page scripts keep working on the same nodes.
 */
(function (root) {
    'use strict';

    const isMarker = function (n) { return n.hasAttribute('data-pane'); };

    // Pure: the marker and its following siblings up to the next marker.
    function paneNodes(marker, markerTest) {
        const out = [marker];
        let n = marker.nextElementSibling;
        while (n && !markerTest(n)) { out.push(n); n = n.nextElementSibling; }
        return out;
    }

    // Pure: "2025-11-24" -> "24/11/25"; "" -> "".
    function shortDate(v) {
        const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(v || '');
        return m ? m[3] + '/' + m[2] + '/' + m[1].slice(2) : '';
    }

    function lastNumber(text) {
        const m = (text || '').match(/\d+/g);
        return m ? m[m.length - 1] : '';
    }

    if (typeof document === 'undefined') {
        root.PhoneNative = { paneNodes: paneNodes, shortDate: shortDate, lastNumber: lastNumber };
        return;
    }
    if (!document.documentElement.dataset.variant) return;

    const mq = window.matchMedia('(max-width: 600px)');
    let undo = [];

    function el(tag, attrs, children) {
        const e = document.createElement(tag);
        Object.keys(attrs || {}).forEach(function (k) {
            if (k === 'text') e.textContent = attrs[k]; else e.setAttribute(k, attrs[k]);
        });
        (children || []).forEach(function (c) { e.append(c); });
        return e;
    }

    // ---------- Title swap: the bar shows the page title once the h1 has scrolled away ----------
    function titleSwap() {
        const h1 = document.querySelector('.page h1');
        if (!h1 || !window.IntersectionObserver) return;
        const io = new IntersectionObserver(function (e) {
            document.documentElement.classList.toggle('is-scrolled', !e[0].isIntersecting);
        });
        io.observe(h1);
        undo.push(function () { io.disconnect(); document.documentElement.classList.remove('is-scrolled'); });
    }

    // ---------- Segmented panes ----------
    function panes() {
        const markers = Array.prototype.slice.call(document.querySelectorAll('[data-pane]'));
        if (markers.length < 2) return;
        const list = markers.map(function (m) { return { label: m.getAttribute('data-pane'), nodes: paneNodes(m, isMarker), count: m.getAttribute('data-pane-count') }; });
        const seg = el('div', { class: 'seg', role: 'tablist' });
        const tabs = list.map(function (p, i) {
            const id = p.nodes[0].id || 'pane-' + i;
            if (!p.nodes[0].id) { p.nodes[0].id = id; undo.push(function () { p.nodes[0].removeAttribute('id'); }); }
            const tab = el('button', { type: 'button', role: 'tab', id: 'tab-' + i, 'aria-controls': id, 'aria-selected': 'false', tabindex: '-1' });
            tab.append(el('span', { text: p.label }), el('span', { class: 'seg__n num' }));
            tab.addEventListener('click', function () { select(i); });
            tab.addEventListener('keydown', function (e) {
                const to = { ArrowRight: i + 1, ArrowLeft: i - 1, Home: 0, End: list.length - 1 }[e.key];
                if (to === undefined) return;
                e.preventDefault();
                select((to + list.length) % list.length, true);
            });
            seg.append(tab);
            p.nodes.forEach(function (n) { if (n.classList.contains('sheet-open')) return; n.setAttribute('role', 'tabpanel'); n.setAttribute('aria-labelledby', 'tab-' + i); });
            const src = p.count && document.getElementById(p.count);
            if (src) {
                const sync = function () { const n = lastNumber(src.textContent); tab.lastChild.textContent = n ? ' (' + n + ')' : ''; };
                const mo = new MutationObserver(sync);
                mo.observe(src, { childList: true, characterData: true, subtree: true });
                sync();
                undo.push(function () { mo.disconnect(); });
            }
            return tab;
        });
        function select(i, focus) {
            list.forEach(function (p, j) {
                p.nodes.forEach(function (n) { n.classList.toggle('is-pane-off', j !== i); });
                tabs[j].setAttribute('aria-selected', String(j === i));
                tabs[j].tabIndex = j === i ? 0 : -1;
            });
            if (focus) tabs[i].focus();
        }
        list[0].nodes[0].before(seg);
        const want = /^#pane=(\d+)$/.exec(location.hash);
        select(want && +want[1] < list.length ? +want[1] : 0);
        undo.push(function () {
            seg.remove();
            list.forEach(function (p) {
                p.nodes.forEach(function (n) { n.classList.remove('is-pane-off'); n.removeAttribute('role'); n.removeAttribute('aria-labelledby'); });
            });
        });
    }

    // ---------- Filter bottom sheet ----------
    function sheet() {
        const nodes = Array.prototype.slice.call(document.querySelectorAll('[data-sheet]'));
        if (!nodes.length) return;
        const marks = nodes.map(function (n) { const c = document.createComment('sheet'); n.before(c); return c; });
        const btn = el('button', { type: 'button', class: 'sheet-open', 'aria-haspopup': 'dialog' });
        marks[0].before(btn);
        // A node that was a pane marker hands the marker to the button, which stays in the pane.
        const moved = [];
        nodes.forEach(function (n) {
            ['data-pane', 'data-pane-count'].forEach(function (a) {
                if (!n.hasAttribute(a)) return;
                moved.push([n, a, n.getAttribute(a)]);
                btn.setAttribute(a, n.getAttribute(a));
                n.removeAttribute(a);
            });
        });
        const body = el('div', { class: 'sheet__body' });
        const apply = el('button', { type: 'button', class: 'btn btn--primary sheet__apply', text: 'Terapkan' });
        const dlg = el('dialog', { class: 'sheet', 'aria-label': 'Filter' }, [
            el('div', { class: 'sheet__grab', 'aria-hidden': 'true' }), el('div', { class: 'sheet__title', text: 'Filter' }), body,
            el('div', { class: 'sheet__foot' }, [apply])]);
        document.body.append(dlg);

        function label() {
            const start = document.getElementById('start-date');
            if (start) {
                const a = shortDate(start.value);
                const b = shortDate(document.getElementById('end-date').value);
                btn.textContent = 'Filter · ' + (a || b ? (a || '…') + ' – ' + (b || '…') : 'Semua tanggal');
                return;
            }
            let n = 0;
            nodes.forEach(function (node) {
                node.querySelectorAll('select').forEach(function (s) { if (s.selectedIndex > 0) n++; });
            });
            btn.textContent = n ? 'Filter (' + n + ')' : 'Filter';
        }
        function open() {
            nodes.forEach(function (n) { body.append(n); });
            dlg.showModal();
        }
        function out() {
            dlg.classList.add('is-closing');
            setTimeout(function () { if (dlg.open) dlg.close(); }, 300);
        }
        btn.addEventListener('click', open);
        apply.addEventListener('click', function () {
            nodes.forEach(function (n) { if (n.tagName === 'FORM') n.requestSubmit(); });
            out();
        });
        dlg.addEventListener('click', function (e) { if (e.target === dlg) out(); });
        dlg.addEventListener('change', label);
        dlg.addEventListener('click', function () { setTimeout(label, 0); });
        dlg.addEventListener('close', function () {
            dlg.classList.remove('is-closing');
            nodes.forEach(function (n, i) { marks[i].before(n); });
            label();
        });
        label();
        undo.push(function () {
            if (dlg.open) dlg.close();
            nodes.forEach(function (n, i) { marks[i].replaceWith(n); });
            moved.forEach(function (m) { m[0].setAttribute(m[1], m[2]); });
            btn.remove();
            dlg.remove();
        });
    }

    function sync() {
        undo.reverse().forEach(function (f) { f(); });
        undo = [];
        if (!mq.matches) return;
        sheet();
        panes();
        titleSwap();
    }

    function start() { sync(); mq.addEventListener('change', sync); }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
})(typeof window !== 'undefined' ? window : globalThis);
