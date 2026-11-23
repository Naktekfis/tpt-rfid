// Pane builder helpers of static/js/phone-native.js (pure functions, no DOM).
// Run: node --test tests/js/phone_native.test.js
const assert = require('node:assert/strict');
const { test } = require('node:test');
require('../../static/js/phone-native.js');
const P = globalThis.PhoneNative;

function chain(marks) {
    const nodes = marks.map(function (m) { return { m: m, nextElementSibling: null }; });
    nodes.forEach(function (n, i) { n.nextElementSibling = nodes[i + 1] || null; });
    return nodes;
}
const isMarker = function (n) { return n.m; };

test('a pane is its marker plus the siblings up to the next marker', () => {
    const n = chain([true, false, false, true, false]);
    assert.deepEqual(P.paneNodes(n[0], isMarker), [n[0], n[1], n[2]]);
    assert.deepEqual(P.paneNodes(n[3], isMarker), [n[3], n[4]]);
});

test('lastNumber and shortDate', () => {
    assert.equal(P.lastNumber('3 dipinjam · 1 terlambat · 20 alat'), '20');
    assert.equal(P.lastNumber(''), '');
    assert.equal(P.shortDate('2026-11-24'), '24/11/26');
    assert.equal(P.shortDate(''), '');
});
