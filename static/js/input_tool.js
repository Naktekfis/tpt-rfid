/*
 * /admin/input_tool: register one physical unit. Pick or create a tool type,
 * pick a tag from the unknown EPCs in the reader field (/api/presence, every
 * 1 s) or type it, save via POST /api/admin/tool_units. The type photo comes
 * from the webcam (…/photo/capture) or a file upload (…/photo).
 */
(function () {
    'use strict';

    const UI = window.UI;
    const B = window.Board;
    const h = UI.h;
    const CFG = window.INPUT_TOOL_CONFIG || {};
    const POLL_MS = 1000;
    const CAMERA_RETRY_MS = 8000;

    const $ = function (id) { return document.getElementById(id); };

    let types = [];
    let tools = [];
    let unknown = [];
    let selectedEpc = '';
    let lastEpcKey = null;
    let photoBust = Date.now();

    function normalizeEpc(v) {
        return String(v || '').replace(/[\s\-:]/g, '').toUpperCase();
    }

    function groupEpc(epc) {
        return epc.replace(/(.{4})(?=.)/g, '$1 ');
    }

    function currentType() {
        const id = $('type-select').value;
        return types.filter(function (t) { return t.type_id === id; })[0] || null;
    }

    // ---------- Types ----------

    async function loadTypes(selectId) {
        const res = await UI.fetchJSON('/api/admin/tool_types');
        if (!res.success) {
            UI.toast(res.error || 'Jenis alat tidak dapat dimuat', 'danger');
            return;
        }
        types = res.tool_types;
        const sel = $('type-select');
        const keep = selectId || sel.value;
        sel.textContent = '';
        if (!types.length) {
            sel.appendChild(h('option', { value: '', text: 'Belum ada jenis alat' }));
            toggleNewType(true);
        } else {
            types.forEach(function (t) {
                sel.appendChild(h('option', {
                    value: t.type_id,
                    text: t.name + ' (' + t.units + ' unit)',
                }));
            });
            if (keep && types.some(function (t) { return t.type_id === keep; })) sel.value = keep;
        }
        onTypeChange();
    }

    function onTypeChange() {
        const t = currentType();
        $('unit-no').value = t ? t.next_unit_no : '';
        updatePreview();
        renderPhoto();
        renderUnits();
    }

    function toggleNewType(open) {
        const box = $('type-new');
        const show = open === undefined ? box.hidden : open;
        box.hidden = !show;
        $('type-new-btn').setAttribute('aria-expanded', String(show));
        if (show) $('type-name').focus();
    }

    async function saveType() {
        const name = $('type-name').value.trim();
        if (!name) {
            $('type-name').focus();
            return;
        }
        $('type-save').disabled = true;
        try {
            const res = await UI.postJSON('/api/admin/tool_types', { name: name });
            if (!res.success) {
                UI.toast(res.error || 'Jenis alat tidak dapat disimpan', 'danger');
                return;
            }
            $('type-name').value = '';
            toggleNewType(false);
            await loadTypes(res.tool_type.type_id);
            UI.toast('Jenis ' + res.tool_type.name + ' dibuat. Tambahkan foto di sebelah kanan.', 'ok');
            $('unit-no').focus();
        } catch (e) {
            UI.toast('Tidak dapat menghubungi server.', 'danger');
        } finally {
            $('type-save').disabled = false;
        }
    }

    function updatePreview() {
        const t = currentType();
        const n = parseInt($('unit-no').value, 10);
        $('unit-preview').textContent = t && n > 0 ? 'Nama unit: ' + t.name + ' #' + n : '';
    }

    // ---------- Tags in the field ----------

    function renderEpcs() {
        const key = JSON.stringify([unknown, selectedEpc]);
        if (key === lastEpcKey) return;
        lastEpcKey = key;
        const box = $('epc-list');
        box.textContent = '';
        // A picked tag that left the field stays in the list, marked.
        const list = unknown.slice();
        if (selectedEpc && list.indexOf(selectedEpc) < 0) list.unshift(selectedEpc);
        if (!list.length) {
            box.appendChild(h('p', { class: 'empty', text: 'Belum ada tag baru yang terbaca.' }));
            return;
        }
        list.forEach(function (epc) {
            const gone = unknown.indexOf(epc) < 0;
            const input = h('input', {
                type: 'radio', name: 'epc', value: epc, checked: epc === selectedEpc,
                onchange: function () {
                    selectedEpc = epc;
                    $('epc-manual').value = '';
                    renderEpcs();
                    const again = box.querySelector('input[value="' + epc + '"]');
                    if (again) again.focus();
                },
            });
            box.appendChild(h('label', { class: 'epc-option' + (epc === selectedEpc ? ' is-selected' : '') },
                input,
                h('span', { class: 'epc-option__epc num', text: groupEpc(epc) }),
                gone ? h('span', { class: 'muted', text: 'tidak terbaca lagi' }) : null));
        });
    }

    async function pollPresence() {
        try {
            const res = await UI.fetchJSON('/api/presence');
            if (res.success) {
                unknown = res.unknown_epcs || [];
                const toolsKey = JSON.stringify(res.tools);
                if (toolsKey !== JSON.stringify(tools)) {
                    tools = res.tools || [];
                    renderUnits();
                }
                renderEpcs();
            }
        } catch (e) { /* next poll */ }
        setTimeout(pollPresence, POLL_MS);
    }

    async function pollDevices() {
        try {
            const res = await UI.fetchJSON('/api/devices/status');
            const r = (res && res.reader) || {};
            const box = $('banners');
            box.textContent = '';
            if (r.mode === 'serial' && !r.connected) {
                box.appendChild(h('div', { class: 'bar bar--warn', role: 'status' },
                    'Pembaca RFID tidak terhubung. Tag baru tidak akan muncul; ketik EPC secara manual.'));
            }
        } catch (e) { /* next poll */ }
        setTimeout(pollDevices, 5000);
    }

    // ---------- Units of the selected type ----------

    function renderUnits() {
        const t = currentType();
        const body = $('units-body');
        body.textContent = '';
        const mine = t ? tools.filter(function (x) { return x.type_id === t.type_id; }) : [];
        mine.sort(function (a, b) { return (a.unit_no || 0) - (b.unit_no || 0); });
        $('units-count').textContent = mine.length ? mine.length + ' unit' : '';
        if (!mine.length) {
            body.appendChild(h('tr', null, h('td', { class: 'empty', colspan: '3', text: 'Belum ada unit untuk jenis ini.' })));
            return;
        }
        mine.forEach(function (u) {
            const kind = B.markOf(u);
            body.appendChild(h('tr', null,
                h('td', { text: '#' + (u.unit_no || '-') }),
                h('td', { class: 'num epc-cell', text: groupEpc(u.rfid_uid || '') }),
                h('td', null, h('span', { class: 'legend__item' },
                    h('span', { class: 'unit-mark unit-mark--' + kind, 'aria-hidden': 'true' }), B.labelOf(kind)))));
        });
    }

    // ---------- Save unit ----------

    async function saveUnit(ev) {
        ev.preventDefault();
        const err = $('unit-error');
        err.textContent = '';
        $('unit-result').hidden = true;
        const t = currentType();
        if (!t) {
            err.textContent = 'Pilih atau buat jenis alat dulu.';
            $('type-select').focus();
            return;
        }
        const unitNo = parseInt($('unit-no').value, 10);
        if (!(unitNo >= 1 && unitNo <= 999)) {
            err.textContent = 'Nomor unit 1 sampai 999.';
            $('unit-no').focus();
            return;
        }
        const manual = normalizeEpc($('epc-manual').value);
        const epc = manual || selectedEpc;
        if (!epc) {
            err.textContent = 'Pilih tag yang terbaca, atau ketik EPC.';
            $('epc-manual').focus();
            return;
        }
        if (!/^[0-9A-F]{4,64}$/.test(epc)) {
            err.textContent = 'EPC harus berupa heksadesimal (0-9, A-F), 4 sampai 64 karakter.';
            $('epc-manual').focus();
            return;
        }
        const btn = $('unit-save');
        btn.disabled = true;
        try {
            const res = await UI.postJSON('/api/admin/tool_units', { type_id: t.type_id, unit_no: unitNo, epc: epc });
            if (!res.success) {
                err.textContent = res.error || 'Unit tidak dapat disimpan.';
                return;
            }
            const box = $('unit-result');
            box.textContent = '';
            box.appendChild(h('h2', { text: res.tool.name + ' terdaftar.' }));
            box.appendChild(h('p', { class: 'num', text: 'EPC ' + groupEpc(res.tool.rfid_uid) }));
            box.appendChild(h('p', { text: 'Letakkan tag berikutnya untuk unit selanjutnya.' }));
            box.hidden = false;
            box.scrollIntoView({ block: 'nearest' });
            UI.toast(res.tool.name + ' terdaftar.', 'ok');
            selectedEpc = '';
            $('epc-manual').value = '';
            unknown = unknown.filter(function (x) { return x !== epc; });
            lastEpcKey = null;
            renderEpcs();
            await loadTypes(t.type_id);
        } catch (e) {
            err.textContent = 'Tidak dapat menghubungi server.';
        } finally {
            btn.disabled = false;
        }
    }

    // ---------- Photo ----------

    function renderPhoto() {
        const t = currentType();
        $('photo-type-name').textContent = t ? t.name : '';
        const box = $('photo-current');
        const fresh = B.toolPhoto(t && t.photo_url ? t.photo_url + '?t=' + photoBust : '', t ? t.name : '', 'lg');
        box.replaceWith(fresh);
        fresh.id = 'photo-current';
        $('photo-capture').disabled = !t;
        $('photo-upload').disabled = !t;
    }

    async function afterPhoto(res, how) {
        if (!res.success) {
            UI.toast(res.error || 'Foto tidak dapat disimpan', 'danger');
            return;
        }
        photoBust = Date.now();
        await loadTypes(currentType().type_id);
        UI.toast('Foto ' + how + ' disimpan.', 'ok');
    }

    async function capturePhoto() {
        const t = currentType();
        if (!t) return;
        const btn = $('photo-capture');
        btn.disabled = true;
        try {
            await afterPhoto(await UI.postJSON('/api/admin/tool_types/' + t.type_id + '/photo/capture'), 'dari kamera');
        } catch (e) {
            UI.toast('Tidak dapat menghubungi server.', 'danger');
        } finally {
            btn.disabled = false;
        }
    }

    async function uploadPhoto() {
        const t = currentType();
        const file = $('photo-file').files[0];
        if (!t || !file) return;
        const fd = new FormData();
        fd.append('photo', file);
        try {
            await afterPhoto(await UI.postForm('/api/admin/tool_types/' + t.type_id + '/photo', fd), 'dari file');
        } catch (e) {
            UI.toast('Tidak dapat menghubungi server.', 'danger');
        } finally {
            $('photo-file').value = '';
        }
    }

    function startCamera() {
        const img = $('photo-cam-img');
        const label = $('photo-cam-label');
        img.onload = function () {
            label.hidden = true;
            img.hidden = false;
        };
        img.onerror = function () {
            img.hidden = true;
            label.hidden = false;
            label.textContent = 'Kamera tidak tersedia';
            setTimeout(function () { img.src = CFG.cameraStream + '?t=' + Date.now(); }, CAMERA_RETRY_MS);
        };
        img.src = CFG.cameraStream;
    }

    // ---------- Init ----------

    $('type-select').addEventListener('change', onTypeChange);
    $('type-new-btn').addEventListener('click', function () { toggleNewType(); });
    $('type-save').addEventListener('click', saveType);
    $('type-name').addEventListener('keydown', function (e) {
        if (e.key === 'Enter') {
            e.preventDefault();
            saveType();
        }
    });
    $('unit-no').addEventListener('input', updatePreview);
    $('epc-manual').addEventListener('input', function () {
        if ($('epc-manual').value && selectedEpc) {
            selectedEpc = '';
            renderEpcs();
        }
    });
    $('unit-form').addEventListener('submit', saveUnit);
    $('photo-capture').addEventListener('click', capturePhoto);
    $('photo-upload').addEventListener('click', function () { $('photo-file').click(); });
    $('photo-file').addEventListener('change', uploadPhoto);

    loadTypes();
    pollPresence();
    pollDevices();
    startCamera();
})();
