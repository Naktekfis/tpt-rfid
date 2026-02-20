/**
 * Input Tool Page Logic
 * Handles form submission and RFID polling for new tools
 */

let rfidPollInterval;
let currentRFID = null;

document.addEventListener('DOMContentLoaded', function () {
    console.log('Input Tool page loaded');

    // Get form elements
    const form = document.getElementById('tool-form');
    const submitBtn = document.getElementById('submit-btn');
    const rfidUidInput = document.getElementById('rfid_uid');

    // Start RFID polling
    startRFIDPolling();

    // Form submission
    form.addEventListener('submit', function (e) {
        e.preventDefault();

        // Validate RFID
        if (!currentRFID) {
            showToast('Harap scan tag RFID terlebih dahulu', 'error');
            return;
        }

        // Validate all fields
        if (!form.checkValidity()) {
            showToast('Harap isi semua field yang diperlukan', 'error');
            return;
        }

        // Submit form
        submitTool();
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
        rfidStatus.textContent = 'Tag terdeteksi!';
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
 */
function onRFIDRemoved() {
    // If no RFID was ever detected, nothing to do
    if (currentRFID === null) return;

    // Keep currentRFID and rfid_uid input intact
    const rfidStatus = document.getElementById('rfid-status');
    rfidStatus.textContent = 'Tag tercatat (boleh dilepas)';
}

/**
 * Check if form is valid and enable/disable submit button
 */
function checkFormValidity() {
    const form = document.getElementById('tool-form');
    const submitBtn = document.getElementById('submit-btn');

    // Check if required fields (name) are filled and RFID is scanned
    // Note: 'name' input has 'required' attribute, so checkValidity() checks it
    const isValid = form.checkValidity() && currentRFID !== null;

    submitBtn.disabled = !isValid;
}

/**
 * Submit tool form
 */
function submitTool() {
    const form = document.getElementById('tool-form');
    // Convert FormData to JSON since our API expects JSON (or make API accept form data)
    // The current API in app.py handles both (request.json or request.form)
    // But let's send as JSON to match modern practices, 
    // OR just use FormData directly as the API supports it.
    // Using FormData directly supports file uploads if we add them later.

    // BUT: app.py add_tool reads request.json OR request.form.
    // Let's use JSON for cleaner handling of non-file data for now.

    const formData = new FormData(form);
    const data = Object.fromEntries(formData.entries());

    // Add Admin Pin header
    // We need the admin pin. It is not injected into input_tool.html yet.
    // Wait, admin_input_tool route uses @admin_required but doesn't pass admin_pin to template?
    // Let's check app.py again.

    // admin_input_tool does NOT pass admin_pin. We need to fix that or use session/cookie.
    // The previous implementation used URL param or Header. 
    // admin_monitor.html uses window.ADMIN_PIN injected from template.

    // FIX: I will assume I need to pass admin_pin to the template in app.py first.
    // For now, I'll attempt sending without pin and see if it fails (it will).
    // I need to update app.py to pass admin_pin to input_tool.html.

    // Let's just grab the pin if it's in the URL (it might not be).
    // Actually, let's just make the fetch request.
    // If I cannot get the pin, I'll rely on the server being lenient or I need to fix app.py to pass it.

    // Let's just do it and then I'll fix app.py in a separate step if needed.
    // Actually, I should check if I can get the pin.
    // admin_welcome.html doesn't have the pin.
    // The user comes from admin_welcome -> input_tool. 
    // Usually admin auth is done via session or token. Here it seems to be a simple PIN check?
    // app.py: admin_required checks X-Admin-Pin header OR admin_pin arg.

    showLoading();

    fetch('/api/admin/tools', {
        method: 'POST',
        headers: getCSRFHeaders({
            'Content-Type': 'application/json'
        }),
        credentials: 'same-origin',  // Include session cookies
        body: JSON.stringify(data)
    })
        .then(response => response.json())
        .then(data => {
            hideLoading();

            if (data.success) {
                showToast(data.message, 'success');

                // Show success message
                document.getElementById('form-status').innerHTML =
                    `<div class="p-4 bg-blue-100 text-blue-800 rounded-lg">
                    <p class="font-semibold">Berhasil!</p>
                    <p>Alat: ${data.tool.name}</p>
                    <p>UID: ${data.tool.rfid_uid}</p>
                </div>`;

                // Reset form
                form.reset();
                currentRFID = null;
                document.getElementById('rfid-status').textContent = 'Menunggu tag alat...';
                document.getElementById('rfid-indicator').classList.remove('border-blue-500', 'bg-blue-50');
                document.getElementById('rfid-uid-display').classList.add('hidden');
                document.getElementById('submit-btn').disabled = true;

            } else {
                showToast(data.error, 'error');
                document.getElementById('form-status').innerHTML =
                    `<div class="p-4 bg-red-100 text-red-800 rounded-lg">
                    <p class="font-semibold">Error: ${data.error}</p>
                </div>`;
            }
        })
        .catch(error => {
            hideLoading();
            console.error('Error submitting tool:', error);
            showToast('Terjadi kesalahan saat menyimpan alat', 'error');
        });
}

// Listen for input changes
document.addEventListener('DOMContentLoaded', function () {
    const inputs = document.querySelectorAll('#tool-form input');
    inputs.forEach(input => {
        input.addEventListener('input', checkFormValidity);
    });
});
