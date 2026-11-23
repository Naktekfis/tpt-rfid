// UI.labelCells (static/js/ui.js): header text becomes data-label on each td, colspan rows are skipped.
// Run: node --test tests/js/ui_labels.test.js
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');

const SRC = fs.readFileSync(path.join(__dirname, '../../static/js/ui.js'), 'utf8');
const noop = function () {};
const context = { document: { addEventListener: noop, querySelector: noop }, window: { addEventListener: noop }, console, Intl, setInterval, setTimeout, clearTimeout, AbortController, Promise };
context.window.document = context.document;
vm.runInNewContext(SRC, context);
const UI = context.window.UI;

function cell(text) {
    const attrs = {};
    return { textContent: text, attrs, setAttribute(k, v) { attrs[k] = v; } };
}
function table(heads, rows) {
    return { tHead: { rows: [{ cells: heads.map(cell) }] }, tBodies: [{ rows: rows.map(function (r) { return { cells: r.map(cell) }; }) }] };
}

test('labels cells from the header and skips colspan rows', () => {
    const t = table([' Alat ', 'Sejak', 'Tindakan'], [['a', 'b', 'c'], ['Memuat…']]);
    UI.labelCells(t);
    assert.deepEqual(t.tBodies[0].rows[0].cells.map(function (c) { return c.attrs['data-label']; }), ['Alat', 'Sejak', 'Tindakan']);
    assert.deepEqual(t.tBodies[0].rows[1].cells[0].attrs, {});
});

test('a table without thead or tbody is left alone', () => {
    UI.labelCells({ tHead: null, tBodies: [] });
});
