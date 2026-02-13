/**
 * Scan Page Logic
 * Handles two-step workflow: scan student card → scan tool tag → confirm transaction
 */

// State management
let currentStep = 1; // 1: scan student, 2: scan tool, 3: confirm
let studentData = null;
let toolData = null;
let rfidPollInterval = null;

document.addEventListener('DOMContentLoaded', function () {
    console.log('Scan page loaded');

    // Initialize
    initializeWorkflow();

    // Setup event listeners
    document.getElementById('reset-btn').addEventListener('click', resetWorkflow);
    document.getElementById('confirm-btn').addEventListener('click', confirmTransaction);

    // Start RFID polling
    startRFIDPolling();

    // Clean up on page unload
    window.addEventListener('beforeunload', function () {
        stopRFIDPolling();
    });
});

/**
 * Initialize workflow to step 1
 */
function initializeWorkflow() {
    currentStep = 1;
    studentData = null;
    toolData = null;

    updateStepIndicator();
    updateStatusMessage('Silakan scan kartu mahasiswa Anda');

    // Hide everything except student scanner
    document.getElementById('student-info').classList.add('hidden');
    document.getElementById('tool-info').classList.add('hidden');
    document.getElementById('action-container').classList.add('hidden');

    // Reset student scanner to waiting state
    document.getElementById('student-scanner-waiting').classList.remove('hidden');
    document.getElementById('student-scanner-scanned').classList.add('hidden');

    document.getElementById('tool-scanner-container').classList.add('hidden');
}

/**
 * Reset workflow
 */
function resetWorkflow() {
    // Clear RFID
    fetch('/debug/clear')
        .then(() => {
            initializeWorkflow();
            showToast('Reset berhasil', 'info');
        })
        .catch(error => {
            console.error('Error clearing RFID:', error);
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
            // Active step
            stepEl.classList.remove('bg-primary-100', 'text-primary-600', 'bg-blue-500', 'from-blue-500', 'to-blue-600');
            stepEl.classList.add('bg-gradient-to-r', 'from-blue-500', 'to-blue-600', 'text-white');
        } else if (stepNum < currentStep) {
            // Completed step
            stepEl.classList.remove('bg-primary-100', 'text-primary-600', 'from-blue-500', 'to-blue-600', 'bg-gradient-to-r');
            stepEl.classList.add('bg-blue-500', 'text-white');
        } else {
            // Future step
            stepEl.classList.remove('from-blue-500', 'to-blue-600', 'text-white', 'bg-blue-500', 'bg-gradient-to-r');
            stepEl.classList.add('bg-primary-100', 'text-primary-600');
        }
    });
}

/**
 * Update status message
 */
function updateStatusMessage(message, type = 'info') {
    const statusEl = document.getElementById('status-message');

    // Status message box was removed from UI, this function is now a no-op
    // Keeping it for backward compatibility with existing code
    if (!statusEl) return;

    // Remove all type classes
    statusEl.classList.remove('bg-blue-50', 'text-blue-800', 'bg-green-50', 'text-green-800',
        'bg-yellow-50', 'text-yellow-800', 'bg-red-50', 'text-red-800');

    // Add appropriate class
    if (type === 'success') {
        statusEl.classList.add('bg-gradient-to-br', 'from-blue-50', 'to-blue-100', 'border-blue-200', 'text-blue-900');
    } else if (type === 'error') {
        statusEl.classList.add('bg-gradient-to-br', 'from-red-50', 'to-red-100', 'border-red-200', 'text-red-900');
    } else if (type === 'warning') {
        statusEl.classList.add('bg-gradient-to-br', 'from-yellow-50', 'to-yellow-100', 'border-yellow-200', 'text-yellow-900');
    } else {
        statusEl.classList.add('bg-gradient-to-br', 'from-primary-50', 'to-primary-100', 'border-primary-200', 'text-primary-900');
    }

    statusEl.innerHTML = `<p class="font-semibold">${message}</p>`;
}

/**
 * Start RFID polling
 */
function startRFIDPolling() {
    console.log('Starting RFID polling');

    // Poll every 1 second for responsive feedback
    rfidPollInterval = setInterval(checkRFID, 1000);

    // Initial check
    checkRFID();
}

/**
 * Stop RFID polling
 */
function stopRFIDPolling() {
    if (rfidPollInterval) {
        clearInterval(rfidPollInterval);
        rfidPollInterval = null;
    }
}

/**
 * Check for RFID card/tag
 */
function checkRFID() {
    fetch('/api/check_rfid')
        .then(response => response.json())
        .then(data => {
            if (data.success && data.detected && data.uid) {
                handleRFIDDetected(data.uid);
            } else {
                handleRFIDRemoved();
            }
        })
        .catch(error => {
            console.error('Error checking RFID:', error);
        });
}

/**
 * Handle RFID detected
 */
function handleRFIDDetected(uid) {
    if (currentStep === 1) {
        // Scan student card
        fetchStudentData(uid);
    } else if (currentStep === 2) {
        // Scan tool tag
        fetchToolData(uid);
    }
}

/**
 * Handle RFID removed
 */
function handleRFIDRemoved() {
    // No action needed - we keep the displayed state
}

// Scanner status update removed - now using direct show/hide of scanner states

/**
 * Fetch student data by RFID UID
 */
let lastStudentUID = null;
function fetchStudentData(uid) {
    // Prevent duplicate requests
    if (lastStudentUID === uid && studentData) return;
    lastStudentUID = uid;

    fetch('/api/scan_student', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ rfid_uid: uid })
    })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                studentData = data.student;
                displayStudentData();

                // Move to step 2
                currentStep = 2;
                updateStepIndicator();
                updateStatusMessage('Mahasiswa terdeteksi. Silakan scan tag alat', 'success');

                // Clear the RFID reader so the student UID doesn't get
                // picked up again as a tool scan in step 2
                fetch('/debug/clear').catch(err => console.error('Error clearing RFID:', err));

                // Show tool scanner
                document.getElementById('tool-scanner-container').classList.remove('hidden');

            } else {
                showToast(data.error, 'error');
                updateStatusMessage(data.error, 'error');
                lastStudentUID = null; // Allow retry
            }
        })
        .catch(error => {
            console.error('Error fetching student:', error);
            showToast('Gagal mengambil data mahasiswa', 'error');
            lastStudentUID = null;
        });
}

/**
 * Display student data
 */
function displayStudentData() {
    // Main display in transaction section (text only, no photo)
    document.getElementById('student-info').classList.remove('hidden');
    document.getElementById('student-name-main').textContent = studentData.name;
    document.getElementById('student-nim-main').textContent = `NIM: ${studentData.nim}`;

    // Add email to main display
    const emailElement = document.getElementById('student-email-main');
    if (emailElement) {
        emailElement.textContent = studentData.email || '-';
    }

    // Side display: Hide waiting state, show scanned state with photo
    document.getElementById('student-scanner-waiting').classList.add('hidden');
    document.getElementById('student-scanner-scanned').classList.remove('hidden');
    if (studentData.photo_url) {
        document.getElementById('student-photo').src = studentData.photo_url;
    }
}

/**
 * Fetch tool data by RFID UID
 */
let lastToolUID = null;
function fetchToolData(uid) {
    // Prevent duplicate requests
    if (lastToolUID === uid && toolData) return;
    lastToolUID = uid;

    fetch('/api/scan_tool', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ rfid_uid: uid })
    })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                toolData = data.tool;

                // Hide waiting state, show scanned state
                document.getElementById('tool-scanner-waiting').classList.add('hidden');
                document.getElementById('tool-scanner-scanned').classList.remove('hidden');

                displayToolData();

                // Move to step 3
                currentStep = 3;
                updateStepIndicator();
                prepareConfirmation();

            } else {
                showToast(data.error, 'error');
                updateStatusMessage(data.error, 'error');
                lastToolUID = null;
            }
        })
        .catch(error => {
            console.error('Error fetching tool:', error);
            showToast('Gagal mengambil data alat', 'error');
            lastToolUID = null;
        });
}

/**
 * Display tool data
 */
function displayToolData() {
    document.getElementById('tool-info').classList.remove('hidden');
    document.getElementById('tool-name').textContent = toolData.name;
    document.getElementById('tool-category').textContent = `Kategori: ${toolData.category}`;

    // Status badge
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
    const actionContainer = document.getElementById('action-container');

    // Show action button
    actionContainer.classList.remove('hidden');

    // Determine action type
    if (toolData.status === 'available') {
        // Borrow action
        confirmBtn.textContent = 'Confirm Pinjam';
        updateStatusMessage('Klik "Confirm Pinjam" untuk meminjam alat', 'success');
    } else {
        // Return action
        confirmBtn.textContent = 'Confirm Kembalikan';
        updateStatusMessage('Klik "Confirm Kembalikan" untuk mengembalikan alat', 'success');
    }
}

/**
 * Confirm transaction
 */
function confirmTransaction() {
    if (!studentData || !toolData) {
        showToast('Data tidak lengkap', 'error');
        return;
    }

    showLoading();

    // Determine endpoint
    const endpoint = toolData.status === 'available' ? '/api/borrow_tool' : '/api/return_tool';

    fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            student_id: studentData.student_id,
            tool_id: toolData.tool_id
        })
    })
        .then(response => response.json())
        .then(data => {
            hideLoading();

            if (data.success) {
                showToast(data.message, 'success');
                updateStatusMessage(data.message, 'success');

                // Auto-reset after 5 seconds
                setTimeout(() => {
                    resetWorkflow();
                }, 5000);
            } else {
                showToast(data.error, 'error');
                updateStatusMessage(data.error, 'error');
            }
        })
        .catch(error => {
            hideLoading();
            console.error('Error confirming transaction:', error);
            showToast('Terjadi kesalahan', 'error');
        });
}

// Transaction history removed - not needed in this view
