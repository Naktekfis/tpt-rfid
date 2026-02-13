/**
 * Monitor Page JavaScript
 * Handles tool monitoring table, search filtering, status/date filters, and borrower tooltip
 */

// ==================== State ====================
let toolsData = [];
let currentTooltip = null;
let activeStatusFilters = []; // empty = show all (no filter active)
let activeDateFilter = null;  // null, 'yesterday', 'last_week', 'last_month'

// ==================== Initialization ====================
document.addEventListener('DOMContentLoaded', function () {
    fetchToolsData();
    setupSearchFilter();
    setupOutsideClickHandlers();
});

// ==================== Data Fetching ====================

/**
 * Fetch tools status from API
 */
function fetchToolsData() {
    fetch('/api/tools_status')
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                toolsData = data.tools;
                applyAllFilters();
            } else {
                showToast('Gagal memuat data alat', 'error');
                hideTableLoading();
            }
        })
        .catch(error => {
            console.error('Error fetching tools:', error);
            showToast('Terjadi kesalahan saat memuat data', 'error');
            hideTableLoading();
        });
}

function hideTableLoading() {
    const loadingRow = document.getElementById('loading-row');
    if (loadingRow) loadingRow.remove();
}

// ==================== Table Rendering ====================

/**
 * Render tools table with given data
 */
function renderTable(tools) {
    const tbody = document.getElementById('tools-table-body');
    const emptyState = document.getElementById('empty-state');

    hideTableLoading();
    tbody.innerHTML = '';

    if (!tools || tools.length === 0) {
        emptyState.classList.remove('hidden');
        return;
    }

    emptyState.classList.add('hidden');

    // Sort: borrowed first, then alphabetically
    tools.sort((a, b) => {
        if (a.status === 'borrowed' && b.status !== 'borrowed') return -1;
        if (a.status !== 'borrowed' && b.status === 'borrowed') return 1;
        return a.name.localeCompare(b.name);
    });

    tools.forEach(tool => {
        const row = document.createElement('tr');
        row.className = 'hover:bg-primary-50 transition-colors';

        // Tool name (fixed width via table-fixed + w-[20%])
        const nameCell = document.createElement('td');
        nameCell.className = 'px-6 py-4';
        nameCell.innerHTML = `<span class="text-sm font-semibold text-primary-900 block truncate">${escapeHtml(tool.name)}</span>`;
        row.appendChild(nameCell);

        // Status badge
        const statusCell = document.createElement('td');
        statusCell.className = 'px-6 py-4';
        statusCell.innerHTML = getStatusBadge(tool.status);
        row.appendChild(statusCell);

        // Borrower name (truncated, clickable)
        const borrowerCell = document.createElement('td');
        borrowerCell.className = 'px-6 py-4';
        if (tool.status === 'borrowed' && tool.borrower_name) {
            const truncatedName = truncateText(tool.borrower_name, 25);
            borrowerCell.innerHTML = `
                <span class="text-sm text-primary-700 cursor-pointer hover:text-primary-900 hover:underline font-medium inline-block truncate max-w-full"
                      data-borrower-name="${escapeHtml(tool.borrower_name)}"
                      data-borrower-nim="${escapeHtml(tool.borrower_nim || '-')}"
                      onclick="showBorrowerTooltip(event, this)">
                    ${escapeHtml(truncatedName)}
                </span>
            `;
        } else {
            borrowerCell.innerHTML = '<span class="text-sm text-primary-400">-</span>';
        }
        row.appendChild(borrowerCell);

        // Borrow time
        const timeCell = document.createElement('td');
        timeCell.className = 'px-6 py-4';
        if (tool.status === 'borrowed' && tool.borrow_time) {
            timeCell.innerHTML = `<span class="text-sm text-primary-700 block truncate">${formatBorrowTime(tool.borrow_time)}</span>`;
        } else {
            timeCell.innerHTML = '<span class="text-sm text-primary-400">-</span>';
        }
        row.appendChild(timeCell);

        tbody.appendChild(row);
    });
}

/**
 * Get status badge HTML
 */
function getStatusBadge(status) {
    if (status === 'available') {
        return '<span class="px-3 py-1 rounded-full text-xs font-bold bg-green-100 text-green-700 border border-green-300 whitespace-nowrap">Tersedia</span>';
    } else if (status === 'borrowed') {
        return '<span class="px-3 py-1 rounded-full text-xs font-bold bg-orange-100 text-orange-700 border border-orange-300 whitespace-nowrap">Dipinjam</span>';
    }
    return '<span class="px-3 py-1 rounded-full text-xs font-bold bg-gray-100 text-gray-700 border border-gray-300">-</span>';
}

// ==================== Filter Logic ====================

/**
 * Apply all active filters combined and re-render table
 */
function applyAllFilters() {
    let filtered = [...toolsData];

    // 1. Status filter
    if (activeStatusFilters.length > 0) {
        filtered = filtered.filter(tool => activeStatusFilters.includes(tool.status));
    }

    // 2. Date filter
    if (activeDateFilter) {
        const dateRange = calculateDateRange(activeDateFilter);
        if (dateRange) {
            filtered = filtered.filter(tool => {
                if (!tool.borrow_time) return false;
                const borrowDate = parseBorrowTime(tool.borrow_time);
                if (!borrowDate) return false;
                return borrowDate >= dateRange.start && borrowDate <= dateRange.end;
            });
        }
    }

    // 3. Text search (name, borrower, NIM)
    const searchTerm = document.getElementById('search-input').value.toLowerCase().trim();
    if (searchTerm) {
        filtered = filtered.filter(tool => {
            const nameMatch = tool.name && tool.name.toLowerCase().includes(searchTerm);
            const borrowerMatch = tool.borrower_name && tool.borrower_name.toLowerCase().includes(searchTerm);
            const nimMatch = tool.borrower_nim && tool.borrower_nim.toLowerCase().includes(searchTerm);
            return nameMatch || borrowerMatch || nimMatch;
        });
    }

    renderTable(filtered);
    updateActiveFiltersBar();
}

/**
 * Calculate date range for a given filter type
 */
function calculateDateRange(filterType) {
    const now = new Date();
    const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 0, 0, 0);
    const todayEnd = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 23, 59, 59);

    switch (filterType) {
        case 'yesterday': {
            const yesterdayStart = new Date(todayStart);
            yesterdayStart.setDate(yesterdayStart.getDate() - 1);
            const yesterdayEnd = new Date(todayEnd);
            yesterdayEnd.setDate(yesterdayEnd.getDate() - 1);
            return { start: yesterdayStart, end: yesterdayEnd };
        }
        case 'last_week': {
            const weekAgo = new Date(todayStart);
            weekAgo.setDate(weekAgo.getDate() - 7);
            return { start: weekAgo, end: todayEnd };
        }
        case 'last_month': {
            const monthAgo = new Date(todayStart);
            monthAgo.setDate(monthAgo.getDate() - 30);
            return { start: monthAgo, end: todayEnd };
        }
        default:
            return null;
    }
}

/**
 * Parse borrow time from different possible formats
 */
function parseBorrowTime(timestamp) {
    if (!timestamp) return null;
    if (timestamp._seconds) return new Date(timestamp._seconds * 1000);
    if (timestamp.seconds) return new Date(timestamp.seconds * 1000);
    const d = new Date(timestamp);
    return isNaN(d.getTime()) ? null : d;
}

// ==================== Search ====================

/**
 * Setup search input listener
 */
function setupSearchFilter() {
    const searchInput = document.getElementById('search-input');
    const resetBtn = document.getElementById('search-reset-btn');

    searchInput.addEventListener('input', function () {
        // Show/hide reset button
        if (this.value.length > 0) {
            resetBtn.classList.remove('hidden');
            resetBtn.classList.add('flex');
        } else {
            resetBtn.classList.add('hidden');
            resetBtn.classList.remove('flex');
        }
        applyAllFilters();
    });
}

/**
 * Reset search input
 */
function resetSearch() {
    const searchInput = document.getElementById('search-input');
    const resetBtn = document.getElementById('search-reset-btn');
    searchInput.value = '';
    resetBtn.classList.add('hidden');
    resetBtn.classList.remove('flex');
    applyAllFilters();
}

// ==================== Status Filter ====================

/**
 * Toggle status dropdown visibility
 */
function toggleStatusDropdown(event) {
    event.stopPropagation();
    const dropdown = document.getElementById('status-dropdown');
    const dateDropdown = document.getElementById('date-dropdown');

    // Close date dropdown if open
    if (!dateDropdown.classList.contains('hidden')) {
        dateDropdown.classList.add('hidden');
    }

    dropdown.classList.toggle('hidden');
}

/**
 * Toggle a status option checkbox
 */
function toggleStatusOption(element) {
    const status = element.getAttribute('data-status');
    const checkBox = element.querySelector('.status-check');
    const checkIcon = checkBox.querySelector('svg');
    const idx = activeStatusFilters.indexOf(status);

    if (idx > -1) {
        // Deselect
        activeStatusFilters.splice(idx, 1);
        checkBox.classList.remove('bg-primary-500', 'border-primary-500');
        checkBox.classList.add('border-primary-300');
        checkIcon.classList.add('hidden');
    } else {
        // Select
        activeStatusFilters.push(status);
        checkBox.classList.add('bg-primary-500', 'border-primary-500');
        checkBox.classList.remove('border-primary-300');
        checkIcon.classList.remove('hidden');
    }

    // Update badge visibility
    const badge = document.getElementById('status-filter-badge');
    const btn = document.getElementById('status-filter-btn');
    if (activeStatusFilters.length > 0) {
        badge.classList.remove('hidden');
        btn.classList.add('border-primary-500', 'bg-primary-50');
        btn.classList.remove('border-primary-200');
    } else {
        badge.classList.add('hidden');
        btn.classList.remove('border-primary-500', 'bg-primary-50');
        btn.classList.add('border-primary-200');
    }

    applyAllFilters();
}

// ==================== Date Filter ====================

/**
 * Toggle date dropdown visibility
 */
function toggleDateDropdown(event) {
    event.stopPropagation();
    const dropdown = document.getElementById('date-dropdown');
    const statusDropdown = document.getElementById('status-dropdown');

    // Close status dropdown if open
    if (!statusDropdown.classList.contains('hidden')) {
        statusDropdown.classList.add('hidden');
    }

    dropdown.classList.toggle('hidden');
}

/**
 * Select a date option (single-select / radio behavior)
 */
function selectDateOption(element) {
    const dateValue = element.getAttribute('data-date');

    // If clicking the same option, deselect it
    if (activeDateFilter === dateValue) {
        activeDateFilter = null;
        clearDateRadioUI();
    } else {
        activeDateFilter = dateValue;
        // Clear all radios first
        clearDateRadioUI();
        // Select current
        const radio = element.querySelector('.date-radio');
        const dot = radio.querySelector('span');
        radio.classList.add('border-primary-500');
        radio.classList.remove('border-primary-300');
        dot.classList.remove('hidden');
    }

    // Update badge visibility
    const badge = document.getElementById('date-filter-badge');
    const btn = document.getElementById('date-filter-btn');
    if (activeDateFilter) {
        badge.classList.remove('hidden');
        btn.classList.add('border-primary-500', 'bg-primary-50');
        btn.classList.remove('border-primary-200');
    } else {
        badge.classList.add('hidden');
        btn.classList.remove('border-primary-500', 'bg-primary-50');
        btn.classList.add('border-primary-200');
    }

    applyAllFilters();
}

/**
 * Clear all date radio UI selections
 */
function clearDateRadioUI() {
    document.querySelectorAll('.date-option').forEach(opt => {
        const radio = opt.querySelector('.date-radio');
        const dot = radio.querySelector('span');
        radio.classList.remove('border-primary-500');
        radio.classList.add('border-primary-300');
        dot.classList.add('hidden');
    });
}

// ==================== Active Filters Bar ====================

/**
 * Update the active filters display bar
 */
function updateActiveFiltersBar() {
    const bar = document.getElementById('active-filters-bar');
    const chips = document.getElementById('active-filter-chips');
    chips.innerHTML = '';

    const hasFilters = activeStatusFilters.length > 0 || activeDateFilter;

    if (!hasFilters) {
        bar.classList.add('hidden');
        return;
    }

    bar.classList.remove('hidden');
    bar.classList.add('flex');

    // Status filter chips
    activeStatusFilters.forEach(status => {
        const label = status === 'borrowed' ? 'Dipinjam' : 'Tersedia';
        const color = status === 'borrowed' ? 'orange' : 'green';
        chips.innerHTML += `
            <span class="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-${color}-100 text-${color}-700 border border-${color}-300">
                ${label}
                <button onclick="removeStatusFilter('${status}')" class="ml-0.5 hover:text-${color}-900 transition-colors">
                    <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
                    </svg>
                </button>
            </span>
        `;
    });

    // Date filter chip
    if (activeDateFilter) {
        const dateLabels = {
            'yesterday': 'Kemarin',
            'last_week': 'Minggu Lalu',
            'last_month': 'Bulan Lalu'
        };
        const label = dateLabels[activeDateFilter] || activeDateFilter;
        chips.innerHTML += `
            <span class="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-primary-100 text-primary-700 border border-primary-300">
                📅 ${label}
                <button onclick="removeDateFilter()" class="ml-0.5 hover:text-primary-900 transition-colors">
                    <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
                    </svg>
                </button>
            </span>
        `;
    }
}

/**
 * Remove a single status filter
 */
function removeStatusFilter(status) {
    const idx = activeStatusFilters.indexOf(status);
    if (idx > -1) {
        activeStatusFilters.splice(idx, 1);
    }

    // Update checkbox UI
    const option = document.querySelector(`.status-option[data-status="${status}"]`);
    if (option) {
        const checkBox = option.querySelector('.status-check');
        const checkIcon = checkBox.querySelector('svg');
        checkBox.classList.remove('bg-primary-500', 'border-primary-500');
        checkBox.classList.add('border-primary-300');
        checkIcon.classList.add('hidden');
    }

    // Update badge
    const badge = document.getElementById('status-filter-badge');
    const btn = document.getElementById('status-filter-btn');
    if (activeStatusFilters.length === 0) {
        badge.classList.add('hidden');
        btn.classList.remove('border-primary-500', 'bg-primary-50');
        btn.classList.add('border-primary-200');
    }

    applyAllFilters();
}

/**
 * Remove date filter
 */
function removeDateFilter() {
    activeDateFilter = null;
    clearDateRadioUI();

    const badge = document.getElementById('date-filter-badge');
    const btn = document.getElementById('date-filter-btn');
    badge.classList.add('hidden');
    btn.classList.remove('border-primary-500', 'bg-primary-50');
    btn.classList.add('border-primary-200');

    applyAllFilters();
}

/**
 * Clear all active filters
 */
function clearAllFilters() {
    // Clear search
    resetSearch();

    // Clear status filters
    activeStatusFilters = [];
    document.querySelectorAll('.status-option').forEach(opt => {
        const checkBox = opt.querySelector('.status-check');
        const checkIcon = checkBox.querySelector('svg');
        checkBox.classList.remove('bg-primary-500', 'border-primary-500');
        checkBox.classList.add('border-primary-300');
        checkIcon.classList.add('hidden');
    });
    const statusBadge = document.getElementById('status-filter-badge');
    const statusBtn = document.getElementById('status-filter-btn');
    statusBadge.classList.add('hidden');
    statusBtn.classList.remove('border-primary-500', 'bg-primary-50');
    statusBtn.classList.add('border-primary-200');

    // Clear date filter
    activeDateFilter = null;
    clearDateRadioUI();
    const dateBadge = document.getElementById('date-filter-badge');
    const dateBtn = document.getElementById('date-filter-btn');
    dateBadge.classList.add('hidden');
    dateBtn.classList.remove('border-primary-500', 'bg-primary-50');
    dateBtn.classList.add('border-primary-200');

    applyAllFilters();
}

// ==================== Borrower Tooltip ====================

/**
 * Show borrower tooltip on click
 */
function showBorrowerTooltip(event, element) {
    event.stopPropagation();

    const borrowerName = element.getAttribute('data-borrower-name');
    const borrowerNIM = element.getAttribute('data-borrower-nim');
    if (!borrowerName) return;

    hideTooltip();

    const tooltip = document.getElementById('borrower-tooltip');
    document.getElementById('tooltip-name').textContent = borrowerName;
    document.getElementById('tooltip-nim').textContent = `NIM: ${borrowerNIM}`;

    // Position near clicked element
    const rect = element.getBoundingClientRect();
    const scrollTop = window.pageYOffset || document.documentElement.scrollTop;
    const scrollLeft = window.pageXOffset || document.documentElement.scrollLeft;

    let top = rect.bottom + scrollTop + 5;
    let left = rect.left + scrollLeft;

    // Keep tooltip on screen
    if (left + 250 > window.innerWidth) {
        left = window.innerWidth - 270;
    }

    tooltip.style.top = top + 'px';
    tooltip.style.left = left + 'px';
    tooltip.classList.remove('hidden');
    currentTooltip = tooltip;
}

/**
 * Hide tooltip
 */
function hideTooltip() {
    if (currentTooltip) {
        currentTooltip.classList.add('hidden');
        currentTooltip = null;
    }
}

// ==================== Outside Click Handlers ====================

/**
 * Setup handlers for closing dropdowns and tooltips on outside click
 */
function setupOutsideClickHandlers() {
    document.addEventListener('click', function (event) {
        const statusDropdown = document.getElementById('status-dropdown');
        const dateDropdown = document.getElementById('date-dropdown');
        const statusBtn = document.getElementById('status-filter-btn');
        const dateBtn = document.getElementById('date-filter-btn');
        const tooltip = document.getElementById('borrower-tooltip');

        // Close status dropdown if click is outside
        if (!statusDropdown.classList.contains('hidden') &&
            !statusDropdown.contains(event.target) &&
            !statusBtn.contains(event.target)) {
            statusDropdown.classList.add('hidden');
        }

        // Close date dropdown if click is outside
        if (!dateDropdown.classList.contains('hidden') &&
            !dateDropdown.contains(event.target) &&
            !dateBtn.contains(event.target)) {
            dateDropdown.classList.add('hidden');
        }

        // Close tooltip if click is outside
        if (tooltip && !tooltip.classList.contains('hidden') &&
            !tooltip.contains(event.target)) {
            hideTooltip();
        }
    });
}

// ==================== Utility Functions ====================

/**
 * Truncate text to max length with ellipsis
 */
function truncateText(text, maxLength) {
    if (!text) return '-';
    if (text.length <= maxLength) return text;
    return text.substring(0, maxLength) + '...';
}

/**
 * Format borrow time to DD-MM-YYYY @HH:MM
 */
function formatBorrowTime(timestamp) {
    const date = parseBorrowTime(timestamp);
    if (!date) return '-';

    const day = String(date.getDate()).padStart(2, '0');
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const year = date.getFullYear();
    const hours = String(date.getHours()).padStart(2, '0');
    const minutes = String(date.getMinutes()).padStart(2, '0');

    return `${day}-${month}-${year} @${hours}:${minutes}`;
}

/**
 * Escape HTML to prevent XSS
 */
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
