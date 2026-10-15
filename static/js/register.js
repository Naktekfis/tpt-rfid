/**
 * Registration Page Logic
 * Handles form submission, photo preview, and RFID polling
 */

let rfidPollInterval;
let currentRFID = null;
let rfidBusy = false;     // a card lookup is in flight
let submitting = false;

function postJSON(url, body) {
    return fetchJSON(url, {
        method: 'POST',
        headers: getCSRFHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify(body)
    });
}

function clearRFIDState() {
    return postJSON('/api/rfid/clear', {});
}

document.addEventListener('DOMContentLoaded', function () {
    console.log('Registration page loaded');

    // Get form elements
    const form = document.getElementById('registration-form');
    const photoInput = document.getElementById('photo');
    const photoPreview = document.getElementById('photo-preview');
    const previewImg = document.getElementById('preview-img');
    const photoName = document.getElementById('photo-name');
    const submitBtn = document.getElementById('submit-btn');
    const rfidIndicator = document.getElementById('rfid-indicator');
    const rfidStatus = document.getElementById('rfid-status');
    const rfidIcon = document.getElementById('rfid-icon');
    const rfidUidDisplay = document.getElementById('rfid-uid-display');
    const rfidUidText = document.getElementById('rfid-uid-text');
    const rfidUidInput = document.getElementById('rfid_uid');

    // Photo preview
    photoInput.addEventListener('change', function (e) {
        const file = e.target.files[0];
        if (file) {
            // Show preview
            const reader = new FileReader();
            reader.onload = function (e) {
                previewImg.src = e.target.result;
                photoPreview.classList.remove('hidden');
            };
            reader.readAsDataURL(file);

            // Show filename
            photoName.textContent = `File: ${file.name}`;

            // Check form validity
            checkFormValidity();
        }
    });

    // Start from a clean reader state so a card or tag from a previous page
    // is not pre-filled, then poll.
    clearRFIDState().catch(() => {}).finally(startRFIDPolling);

    // Form submission
    form.addEventListener('submit', function (e) {
        e.preventDefault();

        // Validate RFID
        if (!currentRFID) {
            showToast('Harap scan kartu RFID terlebih dahulu', 'error');
            return;
        }

        // Validate all fields
        if (!form.checkValidity()) {
            showToast('Harap isi semua field yang diperlukan', 'error');
            return;
        }

        // Submit form
        submitRegistration();
    });

    // Clean up on page unload
    window.addEventListener('beforeunload', function () {
        stopRFIDPolling();
    });
});

/**
 * Start polling for RFID card
 */
function startRFIDPolling() {
    console.log('Starting RFID polling');

    // Poll every 2 seconds
    rfidPollInterval = setInterval(checkRFID, 2000);

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
 * Check for RFID card
 */
function checkRFID() {
    if (rfidBusy || submitting) return;
    fetchJSON('/api/check_rfid')
        .then(data => {
            if (data.success && data.detected && data.uid) {
                // Card detected
                onRFIDDetected(data.uid);
            } else {
                // No card
                onRFIDRemoved();
            }
        })
        .catch(error => {
            console.error('Error checking RFID:', error);
        });
}

/**
 * Handle a tapped card. A card that already belongs to a student or a tool is
 * rejected right away instead of after the whole form is typed. Tapping
 * another card replaces the UID.
 */
async function onRFIDDetected(uid) {
    if (uid === currentRFID) return;
    rfidBusy = true;
    try {
        const [studentRes, toolRes] = await Promise.all([
            postJSON('/api/scan_student', { rfid_uid: uid }),
            postJSON('/api/scan_tool', { rfid_uid: uid }),
        ]);
        if (studentRes.success) {
            setRFIDStatus('Kartu ini sudah terdaftar. Gunakan kartu lain atau langsung pinjam alat.', 'error');
        } else if (toolRes.success) {
            setRFIDStatus('Ini tag alat, bukan KTM. Tap KTM Anda.', 'error');
        } else {
            acceptRFID(uid);
        }
        // Handled: clear so the next tap is a new event.
        await clearRFIDState().catch(() => {});
    } catch (error) {
        console.error('Error checking card:', error);
        setRFIDStatus('Gagal memeriksa kartu. Coba tap lagi.', 'error');
    } finally {
        rfidBusy = false;
    }
}

function setRFIDStatus(message, type) {
    const rfidStatus = document.getElementById('rfid-status');
    rfidStatus.textContent = message;
    rfidStatus.classList.remove('text-gray-600', 'text-primary-700', 'text-blue-600', 'text-red-600');
    rfidStatus.classList.add(type === 'error' ? 'text-red-600' : 'text-blue-600');
}

function acceptRFID(uid) {
    const rfidIndicator = document.getElementById('rfid-indicator');
    const rfidIcon = document.getElementById('rfid-icon');

    currentRFID = uid;

    rfidIndicator.classList.remove('border-gray-300');
    rfidIndicator.classList.add('border-blue-500', 'bg-blue-50');
    rfidIcon.classList.remove('text-gray-400');
    rfidIcon.classList.add('text-blue-500');

    setRFIDStatus('Kartu tercatat (boleh dilepas). Tap kartu lain untuk mengganti.', 'ok');
    document.getElementById('rfid-uid-display').classList.remove('hidden');
    document.getElementById('rfid-uid-text').textContent = uid;
    document.getElementById('rfid_uid').value = uid;

    checkFormValidity();
}

/**
 * No card on the reader. The UID is kept once accepted (the user is filling
 * the form), so there is nothing to do.
 */
function onRFIDRemoved() {}

/**
 * Check if form is valid and enable/disable submit button
 */
function checkFormValidity() {
    const form = document.getElementById('registration-form');
    const submitBtn = document.getElementById('submit-btn');
    const photoInput = document.getElementById('photo');

    // Check if all required fields are filled and RFID is scanned
    const isValid = form.checkValidity() &&
        currentRFID !== null &&
        photoInput.files.length > 0;

    submitBtn.disabled = !isValid || submitting;
}

/**
 * Submit registration form. The button stays disabled while the request runs;
 * errors are shown in #form-status and scrolled into view.
 */
function submitRegistration() {
    if (submitting) return;
    const form = document.getElementById('registration-form');
    const formData = new FormData(form);
    const submitBtn = document.getElementById('submit-btn');

    submitting = true;
    submitBtn.disabled = true;
    showLoading();

    fetchJSON('/api/register', {
        method: 'POST',
        headers: {
            'X-CSRFToken': getCSRFToken()
        },
        body: formData
    })
        .then(data => {
            if (data.success) {
                showFormStatus(
                    ['Registrasi berhasil!', `Nama: ${data.student.name}`, `NIM: ${data.student.nim}`],
                    'success'
                );
                setTimeout(() => {
                    window.location.href = '/';
                }, 3000);
            } else {
                submitting = false;
                showFormStatus([`Gagal: ${data.error}`], 'error');
                checkFormValidity();
            }
        })
        .catch(error => {
            console.error('Error submitting registration:', error);
            submitting = false;
            showFormStatus(['Gagal menghubungi server. Data belum tersimpan, coba lagi.'], 'error');
            checkFormValidity();
        })
        .finally(hideLoading);
}

function showFormStatus(lines, type) {
    const status = document.getElementById('form-status');
    const box = document.createElement('div');
    box.className = type === 'success'
        ? 'p-4 bg-blue-100 text-blue-800 rounded-lg'
        : 'p-4 bg-red-100 text-red-800 rounded-lg';
    box.setAttribute('role', type === 'success' ? 'status' : 'alert');
    lines.forEach((text, i) => {
        const p = document.createElement('p');
        p.textContent = text;
        if (i === 0) p.className = 'font-semibold';
        box.appendChild(p);
    });
    status.replaceChildren(box);
    status.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

// Listen for form field changes to update submit button
document.addEventListener('DOMContentLoaded', function () {
    const inputs = document.querySelectorAll('#registration-form input');
    inputs.forEach(input => {
        input.addEventListener('input', checkFormValidity);
        input.addEventListener('change', checkFormValidity);
    });
});
