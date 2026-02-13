/**
 * Registration Page Logic
 * Handles form submission, photo preview, and RFID polling
 */

let rfidPollInterval;
let currentRFID = null;

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

    // Start RFID polling
    startRFIDPolling();

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
    fetch('/api/check_rfid')
        .then(response => response.json())
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
 * Handle RFID card detected
 */
function onRFIDDetected(uid) {
    const rfidIndicator = document.getElementById('rfid-indicator');
    const rfidStatus = document.getElementById('rfid-status');
    const rfidIcon = document.getElementById('rfid-icon');
    const rfidUidDisplay = document.getElementById('rfid-uid-display');
    const rfidUidText = document.getElementById('rfid-uid-text');
    const rfidUidInput = document.getElementById('rfid_uid');

    // Update UI only if UID changed
    if (currentRFID !== uid) {
        currentRFID = uid;

        // Update indicator
        rfidIndicator.classList.remove('border-gray-300');
        rfidIndicator.classList.add('border-blue-500', 'bg-blue-50');

        // Update icon color
        rfidIcon.classList.remove('text-gray-400');
        rfidIcon.classList.add('text-blue-500');

        // Update status
        rfidStatus.textContent = 'Kartu terdeteksi!';
        rfidStatus.classList.remove('text-gray-600');
        rfidStatus.classList.add('text-blue-600');

        // Show UID
        rfidUidDisplay.classList.remove('hidden');
        rfidUidText.textContent = uid;
        rfidUidInput.value = uid;

        // Check form validity
        checkFormValidity();

        console.log('RFID detected:', uid);
    }
}

/**
 * Handle RFID card removed
 * Once an RFID UID has been detected for registration, we keep the UID value
 * so the user can continue filling the form. Only the visual indicator updates.
 */
function onRFIDRemoved() {
    // If no RFID was ever detected, nothing to do
    if (currentRFID === null) return;

    // Keep currentRFID and rfid_uid input intact — the user is filling the form.
    // Only update the visual indicator to show the card was physically removed,
    // but do NOT clear the UID or disable the submit button.
    const rfidStatus = document.getElementById('rfid-status');
    rfidStatus.textContent = 'Kartu tercatat (boleh dilepas)';
}

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

    submitBtn.disabled = !isValid;
}

/**
 * Submit registration form
 */
function submitRegistration() {
    const form = document.getElementById('registration-form');
    const formData = new FormData(form);

    // Show loading
    showLoading();

    // Submit via AJAX
    fetch('/api/register', {
        method: 'POST',
        body: formData
    })
        .then(response => response.json())
        .then(data => {
            hideLoading();

            if (data.success) {
                showToast(data.message, 'success');

                // Show success message
                document.getElementById('form-status').innerHTML =
                    `<div class="p-4 bg-blue-100 text-blue-800 rounded-lg">
                    <p class="font-semibold">Registrasi berhasil!</p>
                    <p>Nama: ${data.student.name}</p>
                    <p>NIM: ${data.student.nim}</p>
                </div>`;

                // Redirect after 3 seconds
                setTimeout(() => {
                    window.location.href = '/';
                }, 3000);
            } else {
                showToast(data.error, 'error');

                // Show error message
                document.getElementById('form-status').innerHTML =
                    `<div class="p-4 bg-red-100 text-red-800 rounded-lg">
                    <p class="font-semibold">Error: ${data.error}</p>
                </div>`;
            }
        })
        .catch(error => {
            hideLoading();
            console.error('Error submitting registration:', error);
            showToast('Terjadi kesalahan saat registrasi', 'error');
        });
}

// Listen for form field changes to update submit button
document.addEventListener('DOMContentLoaded', function () {
    const inputs = document.querySelectorAll('#registration-form input');
    inputs.forEach(input => {
        input.addEventListener('input', checkFormValidity);
        input.addEventListener('change', checkFormValidity);
    });
});
