/**
 * Scan Page Logic
 * Two-step workflow: scan student card -> scan tool tag -> confirm transaction.
 *
 * One reader reads both card types. Each tap is handled once: after a lookup
 * the server-side UID is cleared, so the next tap (even of the same card)
 * arrives as a new event.
 */

const POLL_MS = 1000;
const IDLE_TIMEOUT_S = 30;      // walk-away reset for steps 2 and 3
const IDLE_WARN_S = 10;         // show the countdown for the last N seconds
const POLL_FAILS_BEFORE_BANNER = 3;
const SUCCESS_RESET_MS = 5000;

// State
let currentStep = 1; // 1: scan student, 2: scan tool, 3: confirm
let studentData = null;
let toolData = null;
let busy = false;        // a lookup or transaction request is in flight
let done = false;        // transaction succeeded, waiting for auto-reset
let lastActivity = Date.now();
let pollFailures = 0;
let pollTimer = null;
let idleTimer = null;

function clearRFIDState() {
    return fetchJSON('/api/rfid/clear', {
        method: 'POST',
        headers: getCSRFHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({})
    });
}

function postJSON(url, body) {
    return fetchJSON(url, {
        method: 'POST',
        headers: getCSRFHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify(body)
    });
}

document.addEventListener('DOMContentLoaded', function () {
    document.getElementById('reset-btn').addEventListener('click', () => resetWorkflow());
    document.getElementById('confirm-btn').addEventListener('click', confirmTransaction);
    document.getElementById('alert-retry').addEventListener('click', confirmTransaction);
    document.getElementById('alert-cancel').addEventListener('click', () => resetWorkflow());

    // Any touch on the page counts as activity for the idle timer.
    document.addEventListener('pointerdown', markActivity);

    // Start from a clean reader state so a tag from another page is not reused.
    clearRFIDState().catch(() => {}).finally(() => {
        initializeWorkflow();
        pollTimer = setInterval(checkRFID, POLL_MS);
        idleTimer = setInterval(checkIdle, 1000);
        checkRFID();
    });

    window.addEventListener('beforeunload', function () {
        clearInterval(pollTimer);
        clearInterval(idleTimer);
    });
});

function markActivity() {
    lastActivity = Date.now();
    hideIdleCountdown();
}

/**
 * Initialize workflow to step 1
 */
function initializeWorkflow() {
    currentStep = 1;
    studentData = null;
    toolData = null;
    busy = false;
    done = false;
    markActivity();
    hideAlert();

    updateStepIndicator();

    document.getElementById('student-info').classList.add('hidden');
    document.getElementById('tool-info').classList.add('hidden');
    document.getElementById('action-container').classList.add('hidden');

    document.getElementById('student-scanner-waiting').classList.remove('hidden');
    document.getElementById('student-scanner-scanned').classList.add('hidden');
    document.getElementById('student-photo').src = document.getElementById('student-photo').dataset.placeholder;

    document.getElementById('tool-scanner-container').classList.add('hidden');
    document.getElementById('tool-scanner-waiting').classList.remove('hidden');
    document.getElementById('tool-scanner-scanned').classList.add('hidden');

    const confirmBtn = document.getElementById('confirm-btn');
    confirmBtn.disabled = false;
}

/**
 * Reset workflow (Reset/Batal button, idle timeout, after success)
 */
function resetWorkflow(message) {
    clearRFIDState()
        .catch(error => console.error('Error clearing RFID:', error))
        .finally(() => {
            initializeWorkflow();
            if (message) showAlert(message, 'info');
        });
}

/**
 * Update step indicator
 */
function updateStepIndicator() {
    const steps = ['step-1', 'step-2', 'step-3'];

    steps.forEach((stepId, index) => {
        const stepEl = document.getElementById(stepId);
        const stepNum = index + 1;

        if (stepNum === currentStep) {
            stepEl.classList.remove('bg-primary-100', 'text-primary-600', 'bg-blue-500', 'from-blue-500', 'to-blue-600');
            stepEl.classList.add('bg-gradient-to-r', 'from-blue-500', 'to-blue-600', 'text-white');
        } else if (stepNum < currentStep) {
            stepEl.classList.remove('bg-primary-100', 'text-primary-600', 'from-blue-500', 'to-blue-600', 'bg-gradient-to-r');
            stepEl.classList.add('bg-blue-500', 'text-white');
        } else {
            stepEl.classList.remove('from-blue-500', 'to-blue-600', 'text-white', 'bg-blue-500', 'bg-gradient-to-r');
            stepEl.classList.add('bg-primary-100', 'text-primary-600');
        }
    });
}

/**
 * In-page alert that stays until the next state change (toasts vanish in 5 s).
 * type: 'error' | 'warning' | 'success' | 'info'. withActions shows Coba lagi / Batal.
 */
const ALERT_STYLES = {
    error: ['bg-red-50', 'border-red-300', 'text-red-900'],
    warning: ['bg-amber-50', 'border-amber-300', 'text-amber-900'],
    success: ['bg-green-50', 'border-green-300', 'text-green-900'],
    info: ['bg-primary-50', 'border-primary-300', 'text-primary-900'],
};

function showAlert(message, type = 'error', withActions = false) {
    const box = document.getElementById('scan-alert');
    Object.values(ALERT_STYLES).flat().forEach(c => box.classList.remove(c));
    box.classList.add(...ALERT_STYLES[type]);
    document.getElementById('scan-alert-text').textContent = message;
    document.getElementById('scan-alert-actions').classList.toggle('hidden', !withActions);
    box.classList.remove('hidden');
}

function hideAlert() {
    document.getElementById('scan-alert').classList.add('hidden');
}

/**
 * Idle timeout: a student who walks away must not leave their session open
 * for the next person's tap.
 */
function checkIdle() {
    if (currentStep === 1 || busy || done) {
        hideIdleCountdown();
        return;
    }
    const left = IDLE_TIMEOUT_S - Math.floor((Date.now() - lastActivity) / 1000);
    if (left <= 0) {
        hideIdleCountdown();
        resetWorkflow('Sesi direset karena tidak ada aktivitas. Silakan scan KTM lagi.');
    } else if (left <= IDLE_WARN_S) {
        const el = document.getElementById('idle-countdown');
        el.textContent = `Tidak ada aktivitas, kembali ke awal dalam ${left} detik. Sentuh layar untuk lanjut.`;
        el.classList.remove('hidden');
    }
}

function hideIdleCountdown() {
    document.getElementById('idle-countdown').classList.add('hidden');
}

/**
 * Poll the reader. Shows a banner when the server or the reader is unreachable.
 */
function checkRFID() {
    if (busy || done) return;

    fetchJSON('/api/check_rfid')
        .then(data => {
            if (!data.success) throw new Error(data.error);
            pollFailures = 0;
            setReaderBanner(data.reader_connected === false
                ? 'Reader RFID tidak terhubung. Hubungi petugas lab.'
                : null);
            if (data.detected && data.uid && !busy && !done) {
                handleTap(data.uid);
            }
        })
        .catch(error => {
            pollFailures += 1;
            console.error('Error checking RFID:', error);
            if (pollFailures >= POLL_FAILS_BEFORE_BANNER) {
                setReaderBanner('Tidak terhubung ke server. Mencoba lagi...');
            }
        });
}

function setReaderBanner(message) {
    const banner = document.getElementById('reader-banner');
    if (message) {
        banner.textContent = message;
        banner.classList.remove('hidden');
    } else {
        banner.classList.add('hidden');
    }
}

/**
 * Handle one tap. Looks the UID up as student and as tool, then decides by
 * step, so a card tapped at the wrong step gets a clear message.
 */
async function handleTap(uid) {
    busy = true;
    markActivity();
    try {
        const [studentRes, toolRes] = await Promise.all([
            postJSON('/api/scan_student', { rfid_uid: uid }),
            postJSON('/api/scan_tool', { rfid_uid: uid }),
        ]);
        const student = studentRes.success ? studentRes.student : null;
        const tool = toolRes.success ? toolRes.tool : null;

        if (currentStep === 1) {
            if (student) {
                acceptStudent(student);
            } else if (tool) {
                showAlert(`Ini tag alat (${tool.name}). Tap KTM Anda terlebih dahulu.`, 'warning');
            } else {
                showAlert('Kartu tidak terdaftar. Daftar dulu lewat menu Registrasi.', 'error');
            }
        } else {
            // Steps 2 and 3: a tool tap sets (or replaces) the tool.
            if (tool) {
                acceptTool(tool);
            } else if (student && studentData && student.student_id === studentData.student_id) {
                showAlert('KTM Anda sudah terbaca. Sekarang tap tag alat.', 'info');
            } else if (student) {
                showAlert(`Ini KTM ${student.name}. Tap tag alat, atau tekan Reset untuk ganti mahasiswa.`, 'warning');
            } else {
                showAlert('Tag tidak terdaftar sebagai alat.', 'error');
            }
        }
        // Handled: clear so the next tap of the same tag is a new event.
        await clearRFIDState().catch(() => {});
    } catch (error) {
        // Network error: leave the UID on the server so the next poll retries.
        console.error('Error handling tap:', error);
        showAlert('Gagal menghubungi server. Coba tap lagi.', 'error');
    } finally {
        busy = false;
    }
}

function acceptStudent(student) {
    studentData = student;
    hideAlert();
    displayStudentData();

    currentStep = 2;
    updateStepIndicator();
    document.getElementById('tool-scanner-container').classList.remove('hidden');
}

function acceptTool(tool) {
    toolData = tool;
    hideAlert();

    document.getElementById('tool-scanner-waiting').classList.add('hidden');
    document.getElementById('tool-scanner-scanned').classList.remove('hidden');
    displayToolData();

    currentStep = 3;
    updateStepIndicator();
    prepareConfirmation();
}

/**
 * Display student data
 */
function displayStudentData() {
    document.getElementById('student-info').classList.remove('hidden');
    document.getElementById('student-name-main').textContent = studentData.name;
    document.getElementById('student-nim-main').textContent = `NIM: ${studentData.nim}`;

    const emailElement = document.getElementById('student-email-main');
    if (emailElement) {
        emailElement.textContent = studentData.email || '-';
    }

    document.getElementById('student-scanner-waiting').classList.add('hidden');
    document.getElementById('student-scanner-scanned').classList.remove('hidden');
    if (studentData.photo_url) {
        document.getElementById('student-photo').src = studentData.photo_url;
    }
}

/**
 * Display tool data
 */
function displayToolData() {
    document.getElementById('tool-info').classList.remove('hidden');
    document.getElementById('tool-name').textContent = toolData.name;
    document.getElementById('tool-category').textContent = `Kategori: ${toolData.category}`;

    const statusBadge = document.getElementById('tool-status-badge');
    if (toolData.status === 'available') {
        statusBadge.innerHTML = '<span class="px-4 py-2 rounded-full text-sm font-semibold bg-blue-200 text-blue-800">Tersedia</span>';
    } else {
        statusBadge.innerHTML = '<span class="px-4 py-2 rounded-full text-sm font-semibold bg-amber-200 text-amber-800">Dipinjam</span>';
    }
}

/**
 * Prepare confirmation step
 */
function prepareConfirmation() {
    const confirmBtn = document.getElementById('confirm-btn');
    document.getElementById('action-container').classList.remove('hidden');
    confirmBtn.disabled = false;
    confirmBtn.textContent = toolData.status === 'available' ? 'Confirm Pinjam' : 'Confirm Kembalikan';
}

/**
 * Confirm transaction. The button is disabled while the request runs and
 * after success, so a double tap cannot submit twice.
 */
function confirmTransaction() {
    if (busy || done) return;
    if (!studentData || !toolData) {
        showAlert('Data tidak lengkap. Scan KTM dan tag alat dulu.', 'error');
        return;
    }

    const confirmBtn = document.getElementById('confirm-btn');
    busy = true;
    confirmBtn.disabled = true;
    markActivity();
    hideAlert();
    showLoading();

    const endpoint = toolData.status === 'available' ? '/api/borrow_tool' : '/api/return_tool';

    postJSON(endpoint, { student_id: studentData.student_id, tool_id: toolData.tool_id })
        .then(data => {
            if (data.success) {
                done = true;
                showAlert(`${data.message} Kembali ke awal dalam ${SUCCESS_RESET_MS / 1000} detik.`, 'success');
                setTimeout(() => resetWorkflow(), SUCCESS_RESET_MS);
            } else {
                confirmBtn.disabled = false;
                showAlert(data.error || 'Transaksi gagal.', 'error', true);
            }
        })
        .catch(error => {
            console.error('Error confirming transaction:', error);
            confirmBtn.disabled = false;
            showAlert('Gagal menghubungi server. Transaksi belum tersimpan.', 'error', true);
        })
        .finally(() => {
            busy = false;
            hideLoading();
        });
}
