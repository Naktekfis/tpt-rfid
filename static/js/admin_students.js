/* Student monitoring: NFC binding, loan details and confirmed reminder emails. */
(function () {
    'use strict';
    const UI = window.UI;
    const h = UI.h;
    const CFG = window.ADMIN_STUDENTS_CONFIG;
    const $ = function (id) { return document.getElementById(id); };
    const clock = new Intl.DateTimeFormat('id-ID', {
        timeZone: 'Asia/Jakarta', hour: '2-digit', minute: '2-digit', hour12: false,
    });
    let students = [];
    let tools = [];
    let loaded = false;
    let loading = false;

    function loansFor(student) {
        return tools.filter(function (t) { return t.status === 'borrowed' && t.borrower_nim === student.nim; });
    }

    function person(student) {
        const img = student.photo_url
            ? h('img', { src: student.photo_url, alt: '', loading: 'lazy' })
            : h('span', { class: 'person-cell__blank', 'aria-hidden': 'true' });
        if (student.photo_url) img.onerror = function () { img.onerror = null; img.src = CFG.placeholderPhoto; };
        return h('div', { class: 'person-cell' }, img, h('div', null,
            h('strong', { text: student.name }), h('span', { class: 'sub num', text: student.nim })));
    }

    function confirmation(text) {
        const dialog = $('reminder');
        $('reminder-text').textContent = text;
        return new Promise(function (resolve) {
            dialog.addEventListener('close', function close() {
                dialog.removeEventListener('close', close);
                resolve(dialog.returnValue === 'ok');
            });
            dialog.returnValue = '';
            dialog.showModal();
        });
    }

    async function remind(student, loan, button) {
        const ok = await confirmation('Kirim pengingat pengembalian ' + loan.name + ' ke ' + student.name + ' (' + student.email + ')?');
        if (!ok) return;
        button.disabled = true;
        try {
            const result = await UI.postJSON('/api/admin/send_warning_email', {
                student_name: student.name, student_email: student.email,
                tool_name: loan.name, borrow_date: loan.borrow_time_wib || '',
            });
            UI.toast(result.success ? 'Email pengingat terkirim.' : result.error || 'Pengiriman gagal.', result.success ? 'ok' : 'danger');
        } catch (error) {
            UI.toast('Tidak dapat menghubungi server.', 'danger');
        } finally {
            button.disabled = false;
        }
    }

    function render() {
        const query = $('student-search').value.trim().toLowerCase();
        const filter = $('student-filter').value;
        const rows = students.filter(function (student) {
            const loans = loansFor(student);
            if (filter === 'borrowed' && !loans.length) return false;
            if (filter === 'overdue' && !loans.some(function (t) { return t.is_overdue; })) return false;
            if (filter === 'no-card' && student.has_nfc) return false;
            return !query || [student.name, student.nim, student.email, student.phone].some(function (value) {
                return value && value.toLowerCase().indexOf(query) >= 0;
            });
        });
        $('students-count').textContent = students.length + ' mahasiswa · ' +
            students.filter(function (s) { return s.has_nfc; }).length + ' dengan kartu NFC';
        const body = $('students-body');
        body.textContent = '';
        if (!rows.length) {
            body.appendChild(h('tr', null, h('td', { colspan: '5', class: 'empty', text: students.length ? 'Tidak ada mahasiswa yang cocok dengan pencarian atau filter.' : 'Belum ada mahasiswa terdaftar.' })));
        }
        rows.forEach(function (student) {
            const loans = loansFor(student);
            const details = h('td');
            if (!loans.length) details.appendChild(h('span', { class: 'muted', text: 'Tidak ada pinjaman aktif' }));
            loans.forEach(function (loan) {
                details.appendChild(h('div', null, h('strong', { text: loan.name }),
                    h('span', { class: 'sub' + (loan.is_overdue ? ' status--warn' : ''),
                        text: (loan.is_overdue ? 'Terlambat · ' : 'Batas: ') + UI.formatWibDate(loan.due_at, true) })));
            });
            const actions = h('td', { class: 'actions' });
            if (!student.has_nfc) actions.appendChild(h('a', {
                href: CFG.registerUrl + '?student_id=' + encodeURIComponent(student.student_id), text: 'Daftarkan kartu',
            }));
            if (student.email) loans.forEach(function (loan) {
                const button = h('button', { type: 'button', class: 'linkbtn', text: 'Kirim pengingat: ' + loan.name });
                button.addEventListener('click', function () { remind(student, loan, button); });
                actions.appendChild(button);
            });
            body.appendChild(h('tr', null, h('td', null, person(student)),
                h('td', null, h('span', { text: student.email }), h('span', { class: 'sub num', text: student.phone })),
                h('td', null, h('span', { class: 'status' + (student.has_nfc ? '' : ' status--muted'), text: student.has_nfc ? 'Ada' : 'Belum ada' })),
                details, actions));
        });
    }

    async function load() {
        if (loading) return;
        loading = true;
        try {
            const results = await Promise.all([UI.fetchJSON('/api/admin/students'), UI.fetchJSON('/api/admin/tools_status')]);
            if (results.some(function (r) { return r.error === 'Unauthorized'; })) {
                window.location.href = '/admin/login';
                return;
            }
            if (!results.every(function (r) { return r.success; })) {
                throw new Error('Students unavailable');
            }
            UI.loadNotice('students-error', '');
            loaded = true;
            students = results[0].students || [];
            tools = results[1].tools || [];
            render();
            $('updated').textContent = 'Diperbarui ' + clock.format(new Date()).replace(':', '.');
        } catch (error) {
            UI.loadNotice('students-error', 'Data mahasiswa belum dapat diperbarui. Data terakhir tetap ditampilkan; mencoba kembali otomatis.', load);
            if (!loaded) $('students-body').querySelector('.empty').textContent = 'Data mahasiswa belum tersedia. Coba muat kembali.';
        } finally { loading = false; }
    }
    $('student-search').addEventListener('input', render);
    $('student-filter').addEventListener('change', render);
    load();
    setInterval(load, 15000);
})();
