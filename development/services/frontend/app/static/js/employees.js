/**
 * employeesApp — Alpine.js component for the Employees page.
 *
 * Handles loading, displaying, and interacting with employee data.
 *
 * @returns {Object} Alpine.js component object
 */
function employeesApp() {
    return {
        /** @type {Array<Object>} List of employee objects */
        employees: [],

        /** @type {string} Search query */
        search: '',

        /** @type {number} Current page (1-based) */
        currentPage: 1,

        /** @type {number} Total pages from API */
        totalPages: 1,

        /** @type {number} Records per page */
        perPage: 10,

        /** @type {number} Total matching employees */
        total: 0,

        /** @type {number|null} Debounce timer handle */
        _searchTimer: null,

        /** @type {boolean} Loading state indicator */
        loading: true,

        /** @type {string|null} Error message to display to user */
        error: null,

        // ── Create / Edit modal ──────────────────────────────────────
        /** @type {boolean} Whether the modal is visible */
        modalOpen: false,
        /** @type {boolean} Whether the form is currently submitting */
        saving: false,
        /** @type {string|null} Form-level error message */
        formError: null,
        /** @type {number|null} Employee ID being edited (null = create mode) */
        editingEmployeeId: null,
        /** @type {Object} Form fields for create / edit */
        form: {
            first_name: '',
            last_name: '',
            email: '',
            password: '',
            phone: '',
            position: '',
            hourly_rate: '',
            skills: '',
            notes: ''
        },
        /** @type {{show: boolean, message: string, type: string}} Toast notification */
        toast: { show: false, message: '', type: 'success' },

        // ── Delete modal ─────────────────────────────────────────────
        /** @type {boolean} Whether the delete confirmation modal is visible */
        deleteModalOpen: false,
        /** @type {number|null} Employee ID pending deletion */
        deletingEmployeeId: null,
        /** @type {string} Display name for the delete confirmation */
        deletingEmployeeName: '',
        /** @type {boolean} Whether a delete request is in flight */
        deleting: false,

        // ── Detail slide-over ───────────────────────────────────────
        /** @type {boolean} Whether the detail panel is visible */
        detailOpen: false,
        /** @type {boolean} Whether detail data is loading */
        detailLoading: false,
        /** @type {object|null} The fully loaded employee shown in the panel */
        selectedEmployee: null,

        // ── Permission flags ────────────────────────────────────
        /** @type {boolean} Whether the user can create/invite employees */
        canCreateEmployee: false,
        /** @type {boolean} Whether the user can edit employees */
        canEditEmployee: false,
        /** @type {boolean} Whether the user can delete employees */
        canDeleteEmployee: false,

        /**
         * Initialize the component on page load.
         * Redirects superadmin to the admin portal (no tenant context).
         * Loads permission flags, then fetches employee data from the API.
         *
         * @returns {Promise<void>}
         */
        async init() {
            // Superadmin has no tenant — redirect to admin portal
            if (await getUserRole() === 'superadmin') {
                window.location.href = '/admin';
                return;
            }

            // Load permission flags for UI gating
            if (typeof hasPermission === 'function') {
                const [create, edit, del] = await Promise.all([
                    hasPermission('employees.create'),
                    hasPermission('employees.edit'),
                    hasPermission('employees.delete'),
                ]);
                this.canCreateEmployee = create;
                this.canEditEmployee   = edit;
                this.canDeleteEmployee = del;

                if (typeof updatePermissionStore === 'function') {
                    updatePermissionStore({
                        canCreateEmployee: create,
                        canEditEmployee: edit,
                        canDeleteEmployee: del,
                    });
                }
            }

            await this.loadEmployees();
        },

        /**
         * Load all employees from the backend API.
         * Uses authFetch to automatically inject JWT authentication token.
         * Handles token refresh on 401 errors automatically via authFetch.
         *
         * API Endpoint: GET /api/employees/
         *
         * @returns {Promise<void>}
         * @throws {Error} If authentication fails or server returns error
         */
        async loadEmployees() {
            this.loading = true;
            this.error = null;

            try {
                const params = new URLSearchParams();
                params.set('skip', String((this.currentPage - 1) * this.perPage));
                params.set('limit', String(this.perPage));
                if (this.search.trim()) {
                    params.set('search', this.search.trim());
                }

                // Use authFetch (from base.html) to automatically inject Bearer token
                const resp = await authFetch(`/api/employees/?${params.toString()}`, {
                    method: 'GET',
                    headers: {
                        'Content-Type': 'application/json'
                    }
                });

                // Check for HTTP errors
                if (!resp.ok) {
                    // Handle 401 Unauthorized
                    if (resp.status === 401) {
                        throw new Error('Missing authentication credentials');
                    }

                    // Handle 403 Forbidden
                    if (resp.status === 403) {
                        throw new Error('You do not have permission to view employees');
                    }

                    // Parse error response if available
                    const data = await resp.json().catch(() => null);
                    const errorMsg = data?.detail || data?.message || `Server error (${resp.status})`;
                    throw new Error(errorMsg);
                }

                // Parse successful response
                const data = await resp.json();
                this.employees = Array.isArray(data)
                    ? data
                    : (data.items || []);
                this.total = Number.isFinite(data?.total)
                    ? data.total
                    : this.employees.length;
                this.perPage = Number.isFinite(data?.per_page)
                    ? data.per_page
                    : this.perPage;
                this.totalPages = Number.isFinite(data?.pages)
                    ? data.pages
                    : Math.max(1, Math.ceil(this.total / this.perPage));

                console.log(`Successfully loaded ${this.employees.length} employees`);

            } catch (err) {
                console.error('Failed to load employees:', err);

                // Set user-friendly error message
                if (err.message.includes('authentication')) {
                    this.error = 'Authentication required. Please log in again.';
                } else if (err.message.includes('permission')) {
                    this.error = 'You do not have permission to view employees.';
                } else if (err.message.includes('fetch')) {
                    this.error = 'Unable to connect to server. Please check your connection.';
                } else {
                    this.error = err.message || 'Failed to load employees. Please try again.';
                }
            } finally {
                this.loading = false;
            }
        },

        /**
         * Debounce search input changes before reloading the first page.
         *
         * @returns {void}
         */
        debouncedSearch() {
            if (this._searchTimer) clearTimeout(this._searchTimer);
            this._searchTimer = setTimeout(() => {
                this.currentPage = 1;
                this.loadEmployees();
            }, 300);
        },

        /**
         * Navigate to a specific page if in range.
         *
         * @param {number} page - Target page (1-based)
         * @returns {void}
         */
        goToPage(page) {
            if (page < 1 || page > this.totalPages || page === this.currentPage) return;
            this.currentPage = page;
            this.loadEmployees();
        },

        /**
         * Compute visible page numbers for pagination control.
         *
         * @returns {Array<number>}
         */
        get visiblePages() {
            const maxVisible = 5;
            const pages = [];

            if (this.totalPages <= maxVisible) {
                for (let i = 1; i <= this.totalPages; i++) pages.push(i);
                return pages;
            }

            let start = Math.max(1, this.currentPage - Math.floor(maxVisible / 2));
            let end = start + maxVisible - 1;

            if (end > this.totalPages) {
                end = this.totalPages;
                start = end - maxVisible + 1;
            }

            for (let i = start; i <= end; i++) pages.push(i);
            return pages;
        },

        /**
         * Reset the form to blank defaults.
         *
         * @returns {void}
         */
        resetForm() {
            this.form = {
                first_name: '', last_name: '', email: '', password: '',
                phone: '', position: '', hourly_rate: '', skills: '', notes: ''
            };
            this.formError = null;
        },

        /**
         * Open the modal in "create" mode with empty fields.
         *
         * @returns {void}
         */
        openInviteModal() {
            this.editingEmployeeId = null;
            this.resetForm();
            this.modalOpen = true;
        },

        /**
         * Open the modal in "edit" mode and pre-fill fields from the API.
         *
         * @param {number} employeeId - Primary key of the employee to edit
         * @returns {Promise<void>}
         */
        async openEditModal(employeeId) {
            this.editingEmployeeId = employeeId;
            this.resetForm();
            this.modalOpen = true;

            try {
                const resp = await authFetch(`/api/employees/${employeeId}`);
                if (!resp.ok) throw new Error(`Error ${resp.status}`);

                const data = await resp.json();

                this.form.first_name = data.first_name || '';
                this.form.last_name = data.last_name || '';
                this.form.email = data.email || '';
                this.form.position = data.position || '';
                this.form.hourly_rate = data.hourly_rate != null ? data.hourly_rate : '';
                this.form.skills = data.skills || '';
                this.form.notes = data.notes || '';
            } catch (err) {
                console.error('Failed to load employee for editing:', err);
                this.formError = 'Failed to load employee data.';
            }
        },

        /**
         * Close the create/edit modal and clear transient state.
         *
         * @returns {void}
         */
        closeModal() {
            this.modalOpen = false;
            this.editingEmployeeId = null;
            this.saving = false;
            this.formError = null;
            this.resetForm();
        },

        /**
         * Submit the create/edit form.
         * Calls POST /api/users/invite (create) or PUT /api/employees/{id} (update).
         *
         * @returns {Promise<void>}
         */
        async saveEmployee() {
            this.formError = null;

            if (this.editingEmployeeId) {
                // ── Edit mode ──
                this.saving = true;
                try {
                    const payload = {};
                    if (this.form.position.trim()) payload.position = this.form.position.trim();
                    else payload.position = null;
                    if (this.form.skills.trim()) payload.skills = this.form.skills.trim();
                    else payload.skills = null;
                    if (this.form.notes.trim()) payload.notes = this.form.notes.trim();
                    else payload.notes = null;
                    if (this.form.hourly_rate !== '' && this.form.hourly_rate !== null) {
                        payload.hourly_rate = parseFloat(this.form.hourly_rate);
                    } else {
                        payload.hourly_rate = null;
                    }

                    const resp = await authFetch(`/api/employees/${this.editingEmployeeId}`, {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(payload)
                    });

                    if (!resp.ok) {
                        const data = await resp.json().catch(() => null);
                        throw new Error(data?.detail || `Error ${resp.status}`);
                    }

                    const editedId = this.editingEmployeeId;
                    this.closeModal();
                    await this.loadEmployees();
                    this.showToast('Employee updated successfully!');

                    // Refresh detail panel if this employee is currently shown
                    if (this.detailOpen && this.selectedEmployee?.id === editedId) {
                        await this.loadEmployeeDetail(editedId);
                    }
                } catch (err) {
                    console.error('Failed to update employee:', err);
                    this.formError = err.message || 'Failed to update employee.';
                } finally {
                    this.saving = false;
                }
            } else {
                // ── Create mode ──
                if (!this.form.first_name.trim() || !this.form.last_name.trim() ||
                    !this.form.email.trim()     || !this.form.password.trim()) {
                    this.formError = 'First name, last name, email and password are required.';
                    return;
                }
                if (this.form.password.length < 8) {
                    this.formError = 'Password must be at least 8 characters.';
                    return;
                }

                this.saving = true;
                try {
                    const payload = {
                        first_name: this.form.first_name.trim(),
                        last_name:  this.form.last_name.trim(),
                        email:      this.form.email.trim(),
                        password:   this.form.password
                    };
                    if (this.form.phone.trim())    payload.phone = this.form.phone.trim();
                    if (this.form.position.trim())  payload.position = this.form.position.trim();
                    if (this.form.skills.trim())    payload.skills = this.form.skills.trim();
                    if (this.form.hourly_rate !== '' && this.form.hourly_rate !== null) {
                        payload.hourly_rate = parseFloat(this.form.hourly_rate);
                    }

                    const resp = await authFetch('/api/users/invite', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(payload)
                    });

                    if (!resp.ok) {
                        const data = await resp.json().catch(() => null);
                        throw new Error(data?.detail || `Server error (${resp.status})`);
                    }

                    this.closeModal();
                    await this.loadEmployees();
                    this.showToast('Employee added successfully!');
                } catch (err) {
                    console.error('Failed to invite employee:', err);
                    this.formError = err.message || 'Failed to add employee. Please try again.';
                } finally {
                    this.saving = false;
                }
            }
        },

        /**
         * Show a temporary toast notification.
         *
         * @param {string} message - Text to display
         * @param {string} [type='success'] - 'success' or 'error'
         * @returns {void}
         */
        showToast(message, type = 'success') {
            this.toast = { show: true, message, type };
            setTimeout(() => { this.toast.show = false; }, 3000);
        },

        /**
         * Open the delete confirmation modal.
         *
         * @param {number} employeeId - Employee ID to delete
         * @param {string} employeeName - Display name for the confirmation
         * @returns {void}
         */
        confirmDelete(employeeId, employeeName) {
            this.deletingEmployeeId = employeeId;
            this.deletingEmployeeName = employeeName;
            this.deleteModalOpen = true;
        },

        /**
         * Execute the employee deletion (soft-deletes the linked user).
         *
         * @returns {Promise<void>}
         */
        async deleteEmployee() {
            if (!this.deletingEmployeeId) return;
            this.deleting = true;
            try {
                const response = await authFetch(`/api/employees/${this.deletingEmployeeId}`, {
                    method: 'DELETE',
                });
                if (!response.ok && response.status !== 204) {
                    const errData = await response.json().catch(() => null);
                    throw new Error(errData?.detail || `Error ${response.status}`);
                }
                this.deleteModalOpen = false;
                this.showToast('Employee deactivated successfully.', 'success');
                if (this.selectedEmployee?.id === this.deletingEmployeeId) {
                    this.closeDetail();
                }
                await this.loadEmployees();
            } catch (err) {
                console.error('Failed to delete employee:', err);
                this.showToast(err.message || 'Failed to delete employee.', 'error');
            } finally {
                this.deleting = false;
                this.deletingEmployeeId = null;
                this.deletingEmployeeName = '';
            }
        },

        /**
         * Open the detail slide-over for an employee.
         *
         * @param {number} id - Employee ID to view
         * @returns {void}
         */
        viewEmployee(id) {
            this.detailOpen = true;
            this.loadEmployeeDetail(id);
        },

        /**
         * Fetch a single employee's details and display in the panel.
         *
         * @param {number} id - Employee ID
         * @returns {Promise<void>}
         */
        async loadEmployeeDetail(id) {
            this.detailLoading = true;
            this.selectedEmployee = null;

            try {
                const resp = await authFetch(`/api/employees/${id}`);
                if (!resp.ok) {
                    throw new Error(`Error ${resp.status}`);
                }
                this.selectedEmployee = await resp.json();
            } catch (err) {
                console.error('Failed to load employee detail:', err);
                this.error = 'Failed to load employee details.';
                this.detailOpen = false;
            } finally {
                this.detailLoading = false;
            }
        },

        /**
         * Close the detail slide-over and clear state.
         *
         * @returns {void}
         */
        closeDetail() {
            this.detailOpen = false;
            this.selectedEmployee = null;
        }
    };
}
