/**
 * Customers Alpine.js Application
 *
 * Manages the customer list, search, pagination, CRUD modals,
 * detail slide-over, and note management.  All API calls go through
 * the frontend proxy at ``/api/customers/…`` which forwards them to
 * customer-bl-service.
 *
 * @returns {object} Alpine.js component data & methods
 */
function customersApp() {
    return {
        // ── List state ──────────────────────────────────────────────
        /** @type {Array<object>} Currently displayed customers */
        customers: [],
        /** @type {boolean} Whether the initial load is in progress */
        loading: true,
        /** @type {string|null} Error message for the list view */
        error: null,

        // ── Search & filter ─────────────────────────────────────────
        /** @type {string} Current search query */
        searchQuery: '',
        /** @type {string} Active / Inactive filter ("", "true", "false") */
        statusFilter: '',

        // ── Pagination ──────────────────────────────────────────────
        /** @type {number} Current page (1-based) */
        currentPage: 1,
        /** @type {number} Records per page */
        perPage: 20,
        /** @type {number} Total matching customers */
        totalCustomers: 0,
        /** @type {number} Total pages */
        totalPages: 0,

        // ── Detail slide-over ───────────────────────────────────────
        /** @type {boolean} Whether the detail panel is visible */
        detailOpen: false,
        /** @type {boolean} Whether detail data is loading */
        detailLoading: false,
        /** @type {object|null} The fully enriched customer shown in the panel */
        selectedCustomer: null,

        // ── Notes ───────────────────────────────────────────────────
        /** @type {boolean} Show the "add note" form */
        showNoteForm: false,
        /** @type {string} Content for a new note */
        newNoteContent: '',
        /** @type {boolean} Whether a note is being saved */
        savingNote: false,

        // ── Create / Edit modal ─────────────────────────────────────
        /** @type {boolean} Whether the create/edit modal is open */
        modalOpen: false,
        /** @type {number|null} Customer ID when editing (null = create) */
        editingCustomerId: null,
        /** @type {boolean} Whether a save is in flight */
        saving: false,
        /** @type {string|null} Validation / server error for the form */
        formError: null,
        /** @type {object} Bound form fields */
        form: {
            first_name: '',
            last_name: '',
            email: '',
            phone: '',
            notify_whatsapp: false,
            notify_email: false,
            company: '',
            address: '',
            eircode: '',
            latitude: null,
            longitude: null,
        },

        // ── Delete confirmation ─────────────────────────────────────
        /** @type {boolean} Whether the delete modal is visible */
        deleteModalOpen: false,
        /** @type {number|null} Customer ID queued for deletion */
        deletingCustomerId: null,
        /** @type {string} Display name shown in the confirm dialog */
        deletingCustomerName: '',
        /** @type {boolean} Whether the delete request is in flight */
        deleting: false,

        // ── GDPR (export / anonymize) ───────────────────────────────
        /** @type {boolean} Whether a GDPR operation is in flight */
        gdprLoading: false,
        /** @type {boolean} Whether the anonymize confirmation modal is open */
        anonymizeModalOpen: false,
        /** @type {number|null} Customer ID queued for anonymization */
        anonymizingCustomerId: null,
        /** @type {string} Display name shown in the anonymize dialog */
        anonymizingCustomerName: '',

        // ── Toast notification ──────────────────────────────────────
        /** @type {{show: boolean, message: string, type: string}} */
        toast: { show: false, message: '', type: 'success' },

        // ── Permission flags ────────────────────────────────────────
        /** @type {boolean} Whether the user can create customers */
        canCreateCustomer: false,
        /** @type {boolean} Whether the user can edit customers */
        canEditCustomer: false,
        /** @type {boolean} Whether the user can delete customers */
        canDeleteCustomer: false,
        /** @type {boolean} Whether the user can create notes */
        canCreateNote: false,

        // ── Debounce timer ──────────────────────────────────────────
        /** @type {number|null} setTimeout handle for search debounce */
        _searchTimer: null,
        /** @type {number|null} Most recently requested detail customer ID */
        _currentDetailId: null,

        // ====================================================================
        // Lifecycle
        // ====================================================================

        /**
         * Initialise the component — redirect superadmin (no tenant context),
         * load permission flags, then load the first page of customers.
         */
        async init() {
            // Superadmin has no tenant — redirect to admin portal
            if (
                typeof getUserRole === 'function' &&
                await getUserRole() === 'superadmin'
            ) {
                window.location.href = '/admin';
                return;
            }

            // Load permission flags for UI gating
            if (typeof hasPermission === 'function') {
                const [create, edit, del, note] = await Promise.all([
                    hasPermission('customers.create'),
                    hasPermission('customers.edit'),
                    hasPermission('customers.delete'),
                    hasPermission('notes.create'),
                ]);
                this.canCreateCustomer = create;
                this.canEditCustomer   = edit;
                this.canDeleteCustomer = del;
                this.canCreateNote     = note;

                if (typeof updatePermissionStore === 'function') {
                    updatePermissionStore({
                        canCreateCustomer: create,
                        canEditCustomer: edit,
                        canDeleteCustomer: del,
                        canCreateNote: note,
                    });
                }
            }

            await this.loadCustomers();
        },

        // ====================================================================
        // Data fetching
        // ====================================================================

        /**
         * Fetch customers from the API with the current search, filter
         * and pagination state.
         */
        async loadCustomers() {
            this.loading = true;
            this.error = null;

            // Build query-string
            const params = new URLSearchParams();
            params.set('skip', String((this.currentPage - 1) * this.perPage));
            params.set('limit', String(this.perPage));

            if (this.searchQuery.trim()) {
                params.set('search', this.searchQuery.trim());
            }
            if (this.statusFilter !== '') {
                params.set('is_active', this.statusFilter);
            }

            try {
                const response = await authFetch(`/api/customers/?${params.toString()}`);

                if (!response.ok) {
                    const data = await response.json().catch(() => null);
                    throw new Error(data?.detail || `Error ${response.status}`);
                }

                const data = await response.json();

                // The BL service returns { items, total, page, per_page, pages }
                this.customers = data.items || [];
                this.totalCustomers = data.total || 0;
                this.totalPages = data.pages || 0;
            } catch (err) {
                console.error('Failed to load customers:', err);
                this.error = err.message || 'Failed to load customers.';
            } finally {
                this.loading = false;
            }
        },

        /**
         * Fetch a single customer with enrichment (jobs, notes) and
         * display in the detail panel.
         *
         * @param {number} customerId - Primary key of the customer
         */
        async loadCustomerDetail(customerId) {
            const requestId = customerId;
            this.detailLoading = true;
            this.selectedCustomer = null;

            try {
                const response = await authFetch(`/api/customers/${customerId}`);

                if (!response.ok) {
                    throw new Error(`Error ${response.status}`);
                }

                const detail = await response.json();

                // Ignore stale responses if the user already selected another customer.
                if (this._currentDetailId !== requestId) return;
                this.selectedCustomer = detail;
            } catch (err) {
                console.error('Failed to load customer detail:', err);
                if (this._currentDetailId === requestId) {
                    this.showToast('Failed to load customer details.', 'error');
                }
            } finally {
                if (this._currentDetailId === requestId) {
                    this.detailLoading = false;
                }
            }
        },

        // ====================================================================
        // Search helpers
        // ====================================================================

        /**
         * Debounce search input so we don't fire on every keystroke.
         * Waits 300 ms after the last input event.
         */
        debouncedSearch() {
            if (this._searchTimer) clearTimeout(this._searchTimer);
            this._searchTimer = setTimeout(() => {
                this.currentPage = 1;
                this.loadCustomers();
            }, 300);
        },

        // ====================================================================
        // Pagination
        // ====================================================================

        /**
         * Navigate to the previous page.
         */
        prevPage() {
            if (this.currentPage > 1) {
                this.currentPage--;
                this.loadCustomers();
            }
        },

        /**
         * Navigate to the next page.
         */
        nextPage() {
            if (this.currentPage < this.totalPages) {
                this.currentPage++;
                this.loadCustomers();
            }
        },

        /**
         * Navigate to a specific page number.
         *
         * @param {number} page - Target page (1-based)
         */
        goToPage(page) {
            this.currentPage = page;
            this.loadCustomers();
        },

        /**
         * Compute the page numbers to show in the pagination control.
         * Shows at most 5 pages centred around the current page.
         *
         * @returns {number[]} Array of page numbers to render
         */
        get visiblePages() {
            const maxVisible = 5;
            const pages = [];

            if (this.totalPages <= maxVisible) {
                for (let i = 1; i <= this.totalPages; i++) pages.push(i);
            } else {
                let start = Math.max(1, this.currentPage - Math.floor(maxVisible / 2));
                let end = start + maxVisible - 1;

                if (end > this.totalPages) {
                    end = this.totalPages;
                    start = end - maxVisible + 1;
                }

                for (let i = start; i <= end; i++) pages.push(i);
            }
            return pages;
        },

        // ====================================================================
        // Detail panel
        // ====================================================================

        /**
         * Open the detail slide-over for a customer.
         *
         * @param {number} customerId - Primary key
         */
        viewCustomer(customerId) {
            this.detailOpen = true;
            this.showNoteForm = false;
            this.newNoteContent = '';
            this._currentDetailId = customerId;
            this.loadCustomerDetail(customerId);
        },

        /**
         * Close the detail slide-over and clear state.
         */
        closeDetail() {
            this.detailOpen = false;
            this._currentDetailId = null;
            this.selectedCustomer = null;
        },

        // ====================================================================
        // Create / Edit modal
        // ====================================================================

        /**
         * Open the modal in "create" mode with empty fields.
         */
        openCreateModal() {
            this.editingCustomerId = null;
            this.resetForm();
            this.modalOpen = true;
        },

        /**
         * Open the modal in "edit" mode and pre-fill fields from the API.
         *
         * @param {number} customerId - Primary key of the customer to edit
         */
        async openEditModal(customerId) {
            this.editingCustomerId = customerId;
            this.resetForm();
            this.modalOpen = true;

            try {
                const response = await authFetch(`/api/customers/${customerId}`);
                if (!response.ok) throw new Error(`Error ${response.status}`);

                const data = await response.json();

                // Populate form with existing data
                this.form.first_name = data.first_name || '';
                this.form.last_name = data.last_name || '';
                this.form.email = data.email || '';
                this.form.phone = data.phone || '';
                this.form.company = data.company || '';
                this.form.address = data.address || '';
                this.form.eircode = data.eircode || '';
                this.form.latitude = data.latitude || null;
                this.form.longitude = data.longitude || null;
                this.form.notify_whatsapp = data.notify_whatsapp || false;
                this.form.notify_email = data.notify_email || false;

                // Render map preview if coordinates are available
                if (data.latitude && data.longitude && window.mapsReady) {
                    this.$nextTick(() => {
                        renderStaticMap('customer-map-preview', data.latitude, data.longitude);
                    });
                }
            } catch (err) {
                console.error('Failed to load customer for editing:', err);
                this.formError = 'Failed to load customer data.';
            }
        },

        /**
         * Close the create/edit modal and reset state.
         */
        closeModal() {
            this.modalOpen = false;
            this.editingCustomerId = null;
            this.formError = null;
            this.resetForm();
        },

        /**
         * Reset all form fields to empty strings.
         */
        resetForm() {
            this.form = {
                first_name: '',
                last_name: '',
                email: '',
                phone: '',
                notify_whatsapp: false,
                notify_email: false,
                company: '',
                address: '',
                eircode: '',
                latitude: null,
                longitude: null,
            };
            this.formError = null;

            // Restore map preview placeholder (don't hide — keep the right panel visible)
            var mapEl = document.getElementById('customer-map-preview');
            if (mapEl) {
                mapEl.style.display = '';
                mapEl.innerHTML =
                    '<div class="flex items-center justify-center h-full text-gray-400 text-sm p-4">' +
                    '<div class="text-center">' +
                    '<svg class="mx-auto h-10 w-10 mb-2 text-gray-300" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">' +
                    '<path stroke-linecap="round" stroke-linejoin="round" d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7"/>' +
                    '</svg>' +
                    '<p class="text-xs">Enter an address or eircode<br>to preview location</p>' +
                    '</div></div>';
            }
        },

        /**
         * Submit the create/edit form.  Calls POST (create) or
         * PUT (update) via ``authFetch``.
         */
        async saveCustomer() {
            // Client-side validation
            if (!this.form.first_name.trim() || !this.form.last_name.trim()) {
                this.formError = 'First name and last name are required.';
                return;
            }

            this.saving = true;
            this.formError = null;

            // Build payload — exclude empty optional fields
            const payload = {
                first_name: this.form.first_name.trim(),
                last_name: this.form.last_name.trim(),
            };
            if (this.form.email.trim()) payload.email = this.form.email.trim();
            if (this.form.phone.trim()) payload.phone = this.form.phone.trim();
            payload.notify_whatsapp = !!this.form.notify_whatsapp;
            payload.notify_email = !!this.form.notify_email;
            if (this.form.company.trim()) payload.company = this.form.company.trim();
            if (this.form.address.trim()) payload.address = this.form.address.trim();
            if (this.form.eircode.trim()) payload.eircode = this.form.eircode.trim();
            if (this.form.latitude !== null && this.form.latitude !== '') {
                payload.latitude = parseFloat(this.form.latitude);
                if (isNaN(payload.latitude)) payload.latitude = null;
            }
            if (this.form.longitude !== null && this.form.longitude !== '') {
                payload.longitude = parseFloat(this.form.longitude);
                if (isNaN(payload.longitude)) payload.longitude = null;
            }

            try {
                let url, method;

                if (this.editingCustomerId) {
                    // Update existing customer
                    url = `/api/customers/${this.editingCustomerId}`;
                    method = 'PUT';
                } else {
                    // Create new customer
                    url = '/api/customers/';
                    method = 'POST';
                }

                const response = await authFetch(url, {
                    method,
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload),
                });

                if (!response.ok) {
                    const errData = await response.json().catch(() => null);
                    throw new Error(errData?.detail || `Error ${response.status}`);
                }

                // Success
                this.closeModal();
                await this.loadCustomers();
                this.showToast(
                    this.editingCustomerId
                        ? 'Customer updated successfully.'
                        : 'Customer created successfully.',
                    'success',
                );

                // Refresh detail panel if this customer is currently shown
                if (this.detailOpen && this.selectedCustomer?.id === this.editingCustomerId) {
                    await this.loadCustomerDetail(this.editingCustomerId);
                }
            } catch (err) {
                console.error('Failed to save customer:', err);
                this.formError = err.message || 'Failed to save customer.';
            } finally {
                this.saving = false;
            }
        },

        // ====================================================================
        // Delete
        // ====================================================================

        /**
         * Show the delete confirmation dialog.
         *
         * @param {number} customerId - Primary key
         * @param {string} customerName - Display name for confirmation text
         */
        confirmDelete(customerId, customerName) {
            this.deletingCustomerId = customerId;
            this.deletingCustomerName = customerName;
            this.deleteModalOpen = true;
        },

        /**
         * Execute the delete (soft-delete) and refresh the list.
         */
        async deleteCustomer() {
            if (!this.deletingCustomerId) return;

            this.deleting = true;

            try {
                const response = await authFetch(`/api/customers/${this.deletingCustomerId}`, {
                    method: 'DELETE',
                });

                if (!response.ok && response.status !== 204) {
                    const errData = await response.json().catch(() => null);
                    throw new Error(errData?.detail || `Error ${response.status}`);
                }

                this.deleteModalOpen = false;
                this.showToast('Customer deleted successfully.', 'success');

                // Close detail panel if this customer was being viewed
                if (this.selectedCustomer?.id === this.deletingCustomerId) {
                    this.closeDetail();
                }

                await this.loadCustomers();
            } catch (err) {
                console.error('Failed to delete customer:', err);
                this.showToast(err.message || 'Failed to delete customer.', 'error');
            } finally {
                this.deleting = false;
                this.deletingCustomerId = null;
                this.deletingCustomerName = '';
            }
        },

        // ====================================================================
        // Notes
        // ====================================================================

        /**
         * Add a new note to the currently viewed customer.
         */
        async addNote() {
            try {
                if (!this.newNoteContent.trim() || !this.selectedCustomer) return;

                this.savingNote = true;
                const response = await authFetch(
                    `/api/notes/${this.selectedCustomer.id}`,
                    {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ content: this.newNoteContent.trim() }),
                    },
                );

                if (!response.ok) {
                    throw new Error(`Error ${response.status}`);
                }

                // Refresh customer detail to show new note
                await this.loadCustomerDetail(this.selectedCustomer.id);
                this.newNoteContent = '';
                this.showNoteForm = false;
                if (typeof window.showNotification === 'function') {
                    window.showNotification('Note added', 'success');
                } else {
                    this.showToast('Note added.', 'success');
                }
            } catch (err) {
                console.error('Failed to add note:', err);
                this.showToast('Failed to add note.', 'error');
            } finally {
                this.savingNote = false;
            }
        },

        // ====================================================================
        // Helpers
        // ====================================================================

        /**
         * Build a full name string from a customer object.
         * Falls back to the ``name`` field if ``first_name``/``last_name``
         * are not available (DB-access layer schema).
         *
         * @param {object} customer - Customer data object
         * @returns {string} Formatted full name
         */
        getFullName(customer) {
            if (!customer) return '';
            if (customer.first_name || customer.last_name) {
                return `${customer.first_name || ''} ${customer.last_name || ''}`.trim();
            }
            return customer.name || '';
        },

        /**
         * Extract initials from a customer object (max 2 characters).
         *
         * @param {object} customer - Customer data object
         * @returns {string} Up to two uppercase letters
         */
        getInitials(customer) {
            if (!customer) return '';
            if (customer.first_name || customer.last_name) {
                return (
                    (customer.first_name?.[0] || '') +
                    (customer.last_name?.[0] || '')
                ).toUpperCase();
            }
            // Fallback for DB-layer name field
            const parts = (customer.name || '').split(' ');
            return parts
                .slice(0, 2)
                .map((p) => p[0] || '')
                .join('')
                .toUpperCase();
        },

        // ====================================================================
        // GDPR — Export & Anonymize
        // ====================================================================

        /**
         * Export all data for a customer as a JSON download.
         * @param {number} customerId
         * @param {string} name - Display name for the filename
         */
        async exportCustomerData(customerId, name) {
            if (!customerId) return;
            this.gdprLoading = true;
            try {
                const resp = await authFetch(`/api/customers/${customerId}/export`);
                if (!resp.ok) throw new Error('Export failed');
                const data = await resp.json();
                const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                const safeName = (name || 'customer').replace(/[^a-zA-Z0-9]/g, '_');
                a.download = `customer-${safeName}-export-${new Date().toISOString().slice(0, 10)}.json`;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                URL.revokeObjectURL(url);
                this.showToast('Customer data exported');
            } catch (err) {
                this.showToast(err.message || 'Failed to export data', 'error');
            } finally {
                this.gdprLoading = false;
            }
        },

        /**
         * Open the anonymize confirmation modal.
         * @param {number} customerId
         * @param {string} name
         */
        confirmAnonymize(customerId, name) {
            this.anonymizingCustomerId = customerId;
            this.anonymizingCustomerName = name || 'this customer';
            this.anonymizeModalOpen = true;
        },

        /**
         * Execute the anonymization request for the selected customer.
         */
        async anonymizeCustomer() {
            if (!this.anonymizingCustomerId) return;
            this.gdprLoading = true;
            try {
                const resp = await authFetch(
                    `/api/customers/${this.anonymizingCustomerId}/anonymize`,
                    { method: 'POST' },
                );
                if (!resp.ok) throw new Error('Anonymization failed');
                this.anonymizeModalOpen = false;
                this.showToast('Customer data anonymized (GDPR)');

                // Close the detail panel and refresh the list
                this.detailOpen = false;
                this.selectedCustomer = null;
                await this.loadCustomers();
            } catch (err) {
                this.showToast(err.message || 'Failed to anonymize customer', 'error');
            } finally {
                this.gdprLoading = false;
                this.anonymizingCustomerId = null;
                this.anonymizingCustomerName = '';
            }
        },

        /**
         * Show a temporary toast notification.
         *
         * @param {string} message - Text to display
         * @param {string} [type='success'] - "success" or "error"
         */
        showToast(message, type = 'success') {
            this.toast = { show: true, message, type };
            setTimeout(() => {
                this.toast.show = false;
            }, 3000);
        },
    };
}
