document.addEventListener('DOMContentLoaded', function () {
    const startDateInput = document.getElementById('start-date');
    const endDateInput = document.getElementById('end-date');
    const applyBtn = document.getElementById('btn-apply-filter');
    const tableBody = document.getElementById('transactions-body');
    const emptyState = document.getElementById('empty-state');
    const filterBtns = document.querySelectorAll('.filter-btn');

    const exportCsvBtn = document.getElementById('btn-export-csv');
    const exportXlsxBtn = document.getElementById('btn-export-xlsx');
    const emailExportBtn = document.getElementById('btn-email-export');
    
    // Email modal elements
    const emailModal = document.getElementById('email-modal');
    const emailModalBackdrop = document.getElementById('email-modal-backdrop');
    const closeModalBtn = document.getElementById('close-modal');
    const cancelEmailBtn = document.getElementById('cancel-email');
    const submitEmailBtn = document.getElementById('submit-email');
    const emailInput = document.getElementById('email-input');
    const emailError = document.getElementById('email-error');

    // Initialize with "1 Bulan"
    setQuickFilter('month');

    // Quick Filter Logic
    filterBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            const range = btn.dataset.range;
            setActiveFilterBtn(btn);
            setQuickFilter(range);
            loadData();
        });
    });

    // Manual Filter Logic
    applyBtn.addEventListener('click', () => {
        // Clear active state from quick filters if manual
        filterBtns.forEach(b => b.classList.remove('active'));
        loadData();
    });
    
    // Export Button Click Handlers with Loading State
    exportCsvBtn.addEventListener('click', function(e) {
        e.preventDefault();
        handleExport(this, 'csv');
    });
    
    exportXlsxBtn.addEventListener('click', function(e) {
        e.preventDefault();
        handleExport(this, 'xlsx');
    });
    
    // Email Export Modal Handlers
    emailExportBtn.addEventListener('click', function() {
        openEmailModal();
    });
    
    closeModalBtn.addEventListener('click', function() {
        closeEmailModal();
    });
    
    cancelEmailBtn.addEventListener('click', function() {
        closeEmailModal();
    });
    
    // Close modal when clicking backdrop
    emailModalBackdrop.addEventListener('click', function() {
        closeEmailModal();
    });
    
    // Email input validation on input
    emailInput.addEventListener('input', function() {
        if (emailError.classList.contains('hidden') === false) {
            emailError.classList.add('hidden');
        }
    });
    
    // Submit email export
    submitEmailBtn.addEventListener('click', function() {
        handleEmailExport();
    });
    
    // Allow Enter key to submit
    emailInput.addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            handleEmailExport();
        }
    });

    function setActiveFilterBtn(activeBtn) {
        filterBtns.forEach(b => b.classList.remove('active'));
        activeBtn.classList.add('active');
    }

    function setQuickFilter(range) {
        const end = new Date();
        let start = new Date();

        switch (range) {
            case 'week':
                start.setDate(end.getDate() - 7);
                break;
            case 'month':
                start.setMonth(end.getMonth() - 1);
                break;
            case 'year':
                start.setFullYear(end.getFullYear() - 1);
                break;
            case 'all':
                start = null;
                break;
        }

        if (start) {
            startDateInput.valueAsDate = start;
        } else {
            startDateInput.value = '';
        }
        endDateInput.valueAsDate = end;
    }

    function updateExportLinks() {
        const start = startDateInput.value;
        const end = endDateInput.value;

        let query = '';
        if (start) query += `&start_date=${start}`;
        if (end) query += `&end_date=${end}`;

        exportCsvBtn.href = `/api/admin/export?format=csv${query}`;
        exportXlsxBtn.href = `/api/admin/export?format=xlsx${query}`;
    }
    
    function handleExport(button, format) {
        const start = startDateInput.value;
        const end = endDateInput.value;
        
        // Build URL
        let url = `/api/admin/export?format=${format}`;
        if (start) url += `&start_date=${start}`;
        if (end) url += `&end_date=${end}`;
        
        // Save original button content
        const originalHTML = button.innerHTML;
        const originalClasses = button.className;
        
        // Show loading state
        button.disabled = true;
        button.innerHTML = `
            <svg class="animate-spin h-4 w-4 inline-block mr-2" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
            Exporting...
        `;
        button.className = originalClasses.replace('hover:bg-', 'bg-') + ' opacity-75 cursor-wait';
        
        // Perform fetch to check for errors
        fetch(url)
            .then(response => {
                if (!response.ok) {
                    // If error, parse JSON error message
                    return response.json().then(data => {
                        throw new Error(data.error || 'Export gagal');
                    });
                }
                // If successful, trigger download
                return response.blob().then(blob => {
                    const downloadUrl = window.URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = downloadUrl;
                    a.download = `rekap_peminjaman_${new Date().getTime()}.${format}`;
                    document.body.appendChild(a);
                    a.click();
                    document.body.removeChild(a);
                    window.URL.revokeObjectURL(downloadUrl);
                    
                    // Show success toast
                    showToast(`Export ${format.toUpperCase()} berhasil!`, 'success');
                });
            })
            .catch(error => {
                console.error('Export error:', error);
                showToast(error.message || 'Terjadi kesalahan saat export', 'error');
            })
            .finally(() => {
                // Restore button state
                button.disabled = false;
                button.innerHTML = originalHTML;
                button.className = originalClasses;
            });
    }
    
    function showToast(message, type = 'info') {
        // Simple toast notification
        const toast = document.createElement('div');
        const bgColor = type === 'success' ? 'bg-green-500' : type === 'error' ? 'bg-red-500' : 'bg-blue-500';
        
        toast.className = `fixed bottom-4 right-4 ${bgColor} text-white px-6 py-3 rounded-lg shadow-lg z-50 animate-fade-in`;
        toast.textContent = message;
        
        document.body.appendChild(toast);
        
        setTimeout(() => {
            toast.classList.add('animate-fade-out');
            setTimeout(() => {
                document.body.removeChild(toast);
            }, 300);
        }, 3000);
    }
    
    // Email Modal Functions
    function openEmailModal() {
        emailInput.value = '';
        emailError.classList.add('hidden');
        emailModal.classList.remove('hidden');
        emailModalBackdrop.classList.remove('hidden');
        // Focus on email input after animation
        setTimeout(() => emailInput.focus(), 100);
    }
    
    function closeEmailModal() {
        emailModal.classList.add('hidden');
        emailModalBackdrop.classList.add('hidden');
        emailInput.value = '';
        emailError.classList.add('hidden');
    }
    
    function validateEmail(email) {
        // Standard email validation regex
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        return emailRegex.test(email);
    }
    
    function handleEmailExport() {
        const email = emailInput.value.trim();
        
        // Validate email format
        if (!email) {
            emailError.textContent = 'Email tidak boleh kosong';
            emailError.classList.remove('hidden');
            return;
        }
        
        if (!validateEmail(email)) {
            emailError.textContent = 'Format email tidak valid';
            emailError.classList.remove('hidden');
            return;
        }
        
        // Get date range
        const start = startDateInput.value;
        const end = endDateInput.value;
        
        // Disable submit button and show loading
        const originalHTML = submitEmailBtn.innerHTML;
        submitEmailBtn.disabled = true;
        submitEmailBtn.innerHTML = `
            <svg class="animate-spin h-4 w-4 inline-block mr-2" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
            Mengirim...
        `;
        
        // Send request to backend
        const requestData = {
            email: email,
            start_date: start || null,
            end_date: end || null
        };
        
        fetch('/api/admin/send_export_email', {
            method: 'POST',
            headers: getCSRFHeaders({
                'Content-Type': 'application/json'
            }),
            body: JSON.stringify(requestData)
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                showToast(`Email berhasil dikirim ke ${email}`, 'success');
                closeEmailModal();
            } else {
                throw new Error(data.error || 'Gagal mengirim email');
            }
        })
        .catch(error => {
            console.error('Email export error:', error);
            showToast(error.message || 'Terjadi kesalahan saat mengirim email', 'error');
        })
        .finally(() => {
            // Restore button state
            submitEmailBtn.disabled = false;
            submitEmailBtn.innerHTML = originalHTML;
        });
    }

    function loadData() {
        const start = startDateInput.value;
        const end = endDateInput.value;

        // Show loading state (simple opactiy or keep skeleton)
        tableBody.style.opacity = '0.5';

        updateExportLinks();

        let url = `/api/admin/transactions?`;
        if (start) url += `start_date=${start}&`;
        if (end) url += `end_date=${end}`;

        fetch(url)
            .then(res => res.json())
            .then(data => {
                tableBody.style.opacity = '1';
                if (data.success) {
                    renderTable(data.data);
                } else {
                    console.error('Error:', data.error);
                }
            })
            .catch(err => {
                console.error('Fetch error:', err);
                tableBody.style.opacity = '1';
            });
    }

    function renderTable(transactions) {
        tableBody.innerHTML = '';

        if (transactions.length === 0) {
            emptyState.classList.remove('hidden');
            return;
        }

        emptyState.classList.add('hidden');

        transactions.forEach(t => {
            const row = document.createElement('tr');
            row.className = 'hover:bg-gray-50 transition-colors';

            const isReturned = t.status === 'returned';
            const statusBadge = isReturned
                ? `<span class="px-2 py-1 bg-green-100 text-green-700 rounded-full text-xs font-medium">Dikembalikan</span>`
                : `<span class="px-2 py-1 bg-yellow-100 text-yellow-700 rounded-full text-xs font-medium">Dipinjam</span>`;

            row.innerHTML = `
                <td class="px-6 py-4 whitespace-nowrap text-gray-500 font-mono text-xs">
                    ${t.borrow_time || '-'}
                </td>
                <td class="px-6 py-4">
                    <div class="font-medium text-gray-900">${t.student_name}</div>
                    <div class="text-xs text-gray-500">${t.student_nim}</div>
                </td>
                <td class="px-6 py-4">
                    <div class="text-gray-900">${t.tool_name}</div>
                    <div class="text-xs text-gray-500">${t.tool_category}</div>
                </td>
                <td class="px-6 py-4 text-center">
                    ${statusBadge}
                </td>
                <td class="px-6 py-4 text-gray-500 text-xs">
                    ${t.return_time || '-'}
                </td>
            `;

            tableBody.appendChild(row);
        });
    }

    // Initial load
    loadData();
});
