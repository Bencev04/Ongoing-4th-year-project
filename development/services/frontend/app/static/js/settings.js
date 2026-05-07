/**
 * Settings Page — Alpine.js Component
 * ====================================
 * Four-tab settings page for owner / admin users.
 *
 * Tabs
 * ----
 *  1. **Organisation** — view & edit company details (name, address, phone, email, eircode).
 *  2. **People**       — list team members, reset passwords for subordinate users.
 *  3. **Permissions**  — toggle fine-grained permission grants per non-privileged user.
 *  4. **Audit Logs**   — review tenant activity across jobs, customers, and settings.
 *
 * API endpoints used
 * ------------------
 *  - GET  /api/company                     — fetch company info
 *  - PUT  /api/company                     — update company info
 *  - GET  /api/users/                      — list tenant users
 *  - GET  /api/permissions/catalog         — permission catalog + role defaults
 *  - GET  /api/users/{id}/permissions      — user grants
 *  - PUT  /api/users/{id}/permissions      — bulk-upsert user grants
 *  - GET  /api/audit-logs                  — tenant audit trail
 *  - POST /api/auth/reset-password         — reset another user's password
 */

/**
 * Main Alpine component for the Settings page.
 *
 * @returns {Object} Alpine data object
 */
function settingsApp() {
    return {

        /* ------------------------------------------------------------------ */
        /* Shared UI state                                                     */
        /* ------------------------------------------------------------------ */

        /** @type {string} Active tab key: 'organisation' | 'people' | 'permissions' | 'audit' */
        activeTab: 'organisation',

        /** @type {boolean} Whether the page is loading data */
        loading: false,

        /** @type {boolean} Whether a form submission is in flight */
        submitting: false,

        /** @type {string|null} Global error message (auto-dismissed on next action) */
        error: null,

        /** @type {string|null} Global success toast message */
        successMessage: null,

        /** @type {boolean} True when the current user lacks owner/admin role */
        accessDenied: false,

        /** @type {number|null} ID of the currently logged-in user */
        currentUserId: null,

        /** @type {string|null} Role of the currently logged-in user */
        currentUserRole: null,

        /* ------------------------------------------------------------------ */
        /* Organisation tab state                                              */
        /* ------------------------------------------------------------------ */

        /** @type {{ name: string, address: string, phone: string, email: string, eircode: string }} */
        companyForm: {
            name: '',
            address: '',
            phone: '',
            email: '',
            eircode: '',
        },

        /* ------------------------------------------------------------------ */
        /* People tab state                                                    */
        /* ------------------------------------------------------------------ */

        /** @type {Array<Object>} Full list of tenant users */
        people: [],

        /** @type {string} Search filter for the people table */
        peopleSearch: '',

        /* ------------------------------------------------------------------ */
        /* Password reset modal state                                          */
        /* ------------------------------------------------------------------ */

        /** @type {boolean} Whether the reset-password modal is visible */
        showResetPasswordModal: false,

        /** @type {Object|null} User object whose password is being reset */
        resetPasswordUser: null,

        /** @type {{ newPassword: string, confirmPassword: string }} */
        resetPasswordForm: { newPassword: '', confirmPassword: '' },

        /** @type {string|null} Error message displayed inside the modal */
        resetPasswordError: null,

        /** @type {boolean} Whether the reset-password request is in flight */
        submittingReset: false,

        /* ------------------------------------------------------------------ */
        /* Permissions tab state                                               */
        /* ------------------------------------------------------------------ */

        /**
         * Permission catalog grouped by category.
         * Each entry: { category: string, permissions: [{key, label, description}] }
         * @type {Array<{ category: string, permissions: Array<{ key: string, label: string, description: string }> }>}
         */
        permCatalog: [],

        /** @type {string} ID of the user selected in the permissions tab dropdown */
        selectedPermUserId: '',

        /** @type {Object<string, boolean>} Map of permission key → granted */
        userPermissions: {},

        /* ------------------------------------------------------------------ */
        /* Audit tab state                                                     */
        /* ------------------------------------------------------------------ */

        /** @type {Array<Object>} Tenant audit log entries */
        auditLogs: [],

        /** @type {string} Free-text search applied to loaded audit logs */
        auditSearch: '',

        /** @type {string} Selected action filter for audit logs */
        auditActionFilter: '',

        /** @type {string} Selected resource-type filter for audit logs */
        auditResourceFilter: '',

        /** @type {string} Start date filter (YYYY-MM-DD) */
        auditDateFrom: '',

        /** @type {string} End date filter (YYYY-MM-DD) */
        auditDateTo: '',

        /** @type {number} Current page for audit log pagination */
        auditPage: 1,

        /** @type {number} Items per page for audit logs */
        auditPerPage: 25,

        /** @type {number} Total audit log entries (from server) */
        auditTotal: 0,

        /** @type {number} Total pages available */
        auditTotalPages: 0,

        /** @type {boolean} Whether audit logs are currently loading */
        auditLoading: false,

        /* ------------------------------------------------------------------ */
        /* Notifications tab state                                             */
        /* ------------------------------------------------------------------ */

        /** @type {Object} Organisation notification preferences */
        notifPrefs: {
            reminder_24h: true,
            reminder_1h: true,
            default_whatsapp: false,
            default_email: false,
            notify_on_the_way: false,
            notify_completed: false,
        },

        /** @type {boolean} Whether the notification prefs saved flash is visible */
        notifPrefsSaved: false,

        /** @type {number|null} Debounce timer for saving notification prefs */
        _notifSaveTimer: null,

        /* ------------------------------------------------------------------ */
        /* Computed-like getters                                                */
        /* ------------------------------------------------------------------ */

        /**
         * People filtered by the search term (name or email).
         * @returns {Array<Object>}
         */
        get filteredPeople() {
            const q = this.peopleSearch.toLowerCase().trim();
            if (!q) return this.people;
            return this.people.filter(p => {
                const name = `${p.first_name || ''} ${p.last_name || ''}`.toLowerCase();
                const email = (p.email || '').toLowerCase();
                return name.includes(q) || email.includes(q);
            });
        },

        /**
         * Users eligible for permission management (non-privileged roles).
         * Owner and admin roles bypass permissions, so they don't need grants.
         * @returns {Array<Object>}
         */
        get permissionEligibleUsers() {
            return this.people.filter(p =>
                p.is_active && !['owner', 'admin', 'superadmin'].includes(p.role)
            );
        },

        /**
         * Whether the currently selected user in the permissions tab
         * is a privileged role (owner/admin/superadmin) that bypasses checks.
         * @returns {boolean}
         */
        get selectedUserIsPrivileged() {
            if (!this.selectedPermUserId) return false;
            const user = this.people.find(
                p => String(p.id) === String(this.selectedPermUserId)
            );
            return user ? ['owner', 'admin', 'superadmin'].includes(user.role) : false;
        },

        /**
         * Role string for the selected permissions user (for display).
         * @returns {string}
         */
        get selectedUserRole() {
            if (!this.selectedPermUserId) return '';
            const user = this.people.find(
                p => String(p.id) === String(this.selectedPermUserId)
            );
            return user ? user.role : '';
        },

        /**
         * Unique action values from the loaded tenant audit logs.
         * @returns {Array<string>}
         */
        get auditActionOptions() {
            return [...new Set(this.auditLogs.map(log => log.action).filter(Boolean))].sort();
        },

        /**
         * Unique resource values from the loaded tenant audit logs.
         * @returns {Array<string>}
         */
        get auditResourceOptions() {
            return [...new Set(this.auditLogs.map(log => log.resource_type).filter(Boolean))].sort();
        },

        /**
         * Audit logs filtered by the dropdown filters (action / resource).
         * Search and date range are handled server-side.
         * @returns {Array<Object>}
         */
        get filteredAuditLogs() {
            let logs = this.auditLogs;

            if (this.auditActionFilter) {
                logs = logs.filter(log => log.action === this.auditActionFilter);
            }
            if (this.auditResourceFilter) {
                logs = logs.filter(log => log.resource_type === this.auditResourceFilter);
            }

            return logs;
        },

        /**
         * Format an audit log details object into a human-readable string.
         * @param {Object|null} details - The details JSON blob from the audit log.
         * @returns {string} Formatted key-value or empty string.
         */
        formatAuditDetails(details) {
            if (!details || typeof details !== 'object') return '';
            return Object.entries(details)
                .filter(([, v]) => v !== null && v !== undefined && v !== '')
                .map(([k, v]) => {
                    const label = k.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
                    const val = typeof v === 'object' ? JSON.stringify(v) : String(v);
                    return `${label}: ${val}`;
                })
                .join('\n');
        },

        /**
         * Navigate to a different audit log page.
         * @param {number} page - Target page number.
         * @returns {Promise<void>}
         */
        async goToAuditPage(page) {
            if (page < 1 || page > this.auditTotalPages) return;
            this.auditPage = page;
            await this.loadAuditLogs();
        },

        /**
         * Handle search input — resets to page 1 and reloads.
         * @returns {Promise<void>}
         */
        async applyAuditSearch() {
            this.auditPage = 1;
            await this.loadAuditLogs();
        },

        /**
         * Reset all audit filters and reload from page 1.
         * @returns {Promise<void>}
         */
        async resetAuditFilters() {
            this.auditSearch = '';
            this.auditActionFilter = '';
            this.auditResourceFilter = '';
            this.auditDateFrom = '';
            this.auditDateTo = '';
            this.auditPage = 1;
            await this.loadAuditLogs();
        },

        /* ================================================================== */
        /* Initialisation                                                      */
        /* ================================================================== */

        /**
         * Lifecycle hook — called by Alpine on x-init.
         * Verifies the user has owner/admin access, then loads the first tab.
         *
         * @returns {Promise<void>}
         */
        async init() {
            try {
                const ctx = await getAuthContext();
                if (!ctx || !['owner', 'admin'].includes(ctx.role)) {
                    this.accessDenied = true;
                    return;
                }
                this.currentUserId = ctx.user_id;
                this.currentUserRole = ctx.role;
                await this.loadCompany();
            } catch {
                this.accessDenied = true;
            }
        },

        /* ================================================================== */
        /* Organisation Tab                                                    */
        /* ================================================================== */

        /**
         * Fetch the current company details and populate the form.
         *
         * @returns {Promise<void>}
         */
        async loadCompany() {
            this.loading = true;
            this.error = null;
            try {
                const resp = await authFetch('/api/company');
                if (!resp.ok) {
                    const data = await resp.json().catch(() => null);
                    throw new Error(data?.detail || 'Failed to load company details');
                }
                const company = await resp.json();

                this.companyForm = {
                    name:    company.name    || '',
                    address: company.address || '',
                    phone:   company.phone   || '',
                    email:   company.email   || '',
                    eircode: company.eircode || '',
                };
            } catch (err) {
                this.error = err.message || 'Failed to load company details';
            } finally {
                this.loading = false;
            }
        },

        /**
         * Submit updated company details.
         *
         * @returns {Promise<void>}
         */
        async saveCompany() {
            if (this.submitting) return;
            this.submitting = true;
            this.error = null;
            this.successMessage = null;

            try {
                const resp = await authFetch('/api/company', {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(this.companyForm),
                });

                if (!resp.ok) {
                    const data = await resp.json().catch(() => null);
                    throw new Error(data?.detail || 'Failed to update company');
                }

                this.successMessage = 'Company details saved successfully';
                setTimeout(() => { this.successMessage = null; }, 4000);
            } catch (err) {
                this.error = err.message || 'Failed to update company';
            } finally {
                this.submitting = false;
            }
        },

        /* ================================================================== */
        /* People Tab                                                          */
        /* ================================================================== */

        /**
         * Fetch the list of users in the current tenant.
         *
         * @returns {Promise<void>}
         */
        async loadPeople() {
            this.loading = true;
            this.error = null;
            try {
                const resp = await authFetch('/api/users/');
                if (!resp.ok) {
                    const data = await resp.json().catch(() => null);
                    throw new Error(data?.detail || 'Failed to load users');
                }
                const data = await resp.json();

                // The user-bl returns items in a `users` key or as a top-level array.
                this.people = Array.isArray(data) ? data : (data.users || data.items || []);
            } catch (err) {
                this.error = err.message || 'Failed to load team members';
            } finally {
                this.loading = false;
            }
        },

        /**
         * Open the password-reset modal for a given user.
         *
         * @param {Object} person - The user whose password will be reset
         * @returns {void}
         */
        openResetPasswordModal(person) {
            this.resetPasswordUser = person;
            this.resetPasswordForm = { newPassword: '', confirmPassword: '' };
            this.resetPasswordError = null;
            this.showResetPasswordModal = true;
        },

        /**
         * Submit the password reset request for the selected user.
         * Validates that both passwords match and meet length requirements.
         *
         * @returns {Promise<void>}
         */
        async resetPassword() {
            // Client-side validation
            if (this.resetPasswordForm.newPassword !== this.resetPasswordForm.confirmPassword) {
                this.resetPasswordError = 'Passwords do not match';
                return;
            }
            if (this.resetPasswordForm.newPassword.length < 8) {
                this.resetPasswordError = 'Password must be at least 8 characters';
                return;
            }

            if (this.submittingReset) return;
            this.submittingReset = true;
            this.resetPasswordError = null;

            try {
                const resp = await authFetch('/api/auth/reset-password', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        user_id: this.resetPasswordUser.id,
                        new_password: this.resetPasswordForm.newPassword,
                    }),
                });

                if (!resp.ok) {
                    const data = await resp.json().catch(() => null);
                    throw new Error(data?.detail || 'Password reset failed');
                }

                // Success — close modal & show toast
                this.showResetPasswordModal = false;
                this.successMessage = `Password reset for ${this.resetPasswordUser.email}`;
                setTimeout(() => { this.successMessage = null; }, 4000);
            } catch (err) {
                this.resetPasswordError = err.message || 'Password reset failed';
            } finally {
                this.submittingReset = false;
            }
        },

        /* ================================================================== */
        /* Permissions Tab                                                     */
        /* ================================================================== */

        /**
         * Initial load for the permissions tab.
         * Fetches both the catalog and the people list in parallel.
         *
         * @returns {Promise<void>}
         */
        async loadPermissionsTab() {
            this.loading = true;
            this.error = null;
            this.selectedPermUserId = '';
            this.userPermissions = {};

            try {
                // Load catalog and people list in parallel
                const [catalogResp, peopleResp] = await Promise.all([
                    authFetch('/api/permissions/catalog'),
                    this.people.length === 0
                        ? authFetch('/api/users/')
                        : Promise.resolve(null),
                ]);

                // Process catalog
                if (!catalogResp.ok) {
                    const data = await catalogResp.json().catch(() => null);
                    throw new Error(data?.detail || 'Failed to load permission catalog');
                }
                const catalog = await catalogResp.json();
                this.permCatalog = this._buildCatalogGroups(catalog);

                // Process people (if we needed to fetch)
                if (peopleResp) {
                    if (!peopleResp.ok) {
                        const data = await peopleResp.json().catch(() => null);
                        throw new Error(data?.detail || 'Failed to load users');
                    }
                    const data = await peopleResp.json();
                    this.people = Array.isArray(data) ? data : (data.users || data.items || []);
                }
            } catch (err) {
                this.error = err.message || 'Failed to load permissions';
            } finally {
                this.loading = false;
            }
        },

        /**
         * Transform the flat permission catalog into grouped categories.
         *
         * Permission keys follow the pattern ``<category>.<action>`` (e.g.
         * ``jobs.create``). This method groups them by category and produces
         * human-readable labels.
         *
         * @param {{ permissions: string[], defaults: Object }} catalog
         * @returns {Array<{ category: string, permissions: Array<{ key: string, label: string, description: string }> }>}
         * @private
         */
        _buildCatalogGroups(catalog) {
            /** @type {Object<string, Array<{ key: string, label: string, description: string }>>} */
            const groups = {};

            for (const key of catalog.permissions || []) {
                const [category, ...rest] = key.split('.');
                const action = rest.join('.');

                // Human-readable label (e.g. "jobs.create" → "Create")
                const label = action
                    .replace(/_/g, ' ')
                    .replace(/\b\w/g, c => c.toUpperCase());

                // Friendly description
                const description = `Allow ${action.replace(/_/g, ' ')} for ${category}`;

                if (!groups[category]) groups[category] = [];
                groups[category].push({ key, label, description });
            }

            // Convert to array for Alpine template iteration
            return Object.entries(groups).map(([category, permissions]) => ({
                category: category.charAt(0).toUpperCase() + category.slice(1),
                permissions,
            }));
        },

        /**
         * Load the selected user's permission grants.
         *
         * @returns {Promise<void>}
         */
        async loadUserPermissions() {
            if (!this.selectedPermUserId) {
                this.userPermissions = {};
                return;
            }

            this.loading = true;
            this.error = null;

            try {
                const resp = await authFetch(
                    `/api/users/${this.selectedPermUserId}/permissions`
                );
                if (!resp.ok) {
                    const data = await resp.json().catch(() => null);
                    throw new Error(data?.detail || 'Failed to load user permissions');
                }
                const data = await resp.json();

                // Build a lookup from the grants array.
                // The response shape is { permissions: [{permission, granted}, ...] }
                // or could be a flat map.
                const perms = {};

                if (Array.isArray(data.permissions)) {
                    // Array of { permission: string, granted: boolean }
                    for (const p of data.permissions) {
                        perms[p.permission] = p.granted;
                    }
                } else if (data.permissions && typeof data.permissions === 'object') {
                    // Already a map
                    Object.assign(perms, data.permissions);
                }

                this.userPermissions = perms;
            } catch (err) {
                this.error = err.message || 'Failed to load user permissions';
            } finally {
                this.loading = false;
            }
        },

        /**
         * Toggle a single permission key in the local state.
         * The change is not persisted until ``savePermissions()`` is called.
         *
         * @param {string} key - The permission key (e.g. ``jobs.create``)
         * @returns {void}
         */
        togglePermission(key) {
            this.userPermissions[key] = !this.userPermissions[key];
        },

        /**
         * Persist the current permission toggle state for the selected user.
         * Sends a bulk upsert to the user-bl-service.
         *
         * @returns {Promise<void>}
         */
        async savePermissions() {
            if (this.submitting || !this.selectedPermUserId) return;
            this.submitting = true;
            this.error = null;
            this.successMessage = null;

            try {
                const resp = await authFetch(
                    `/api/users/${this.selectedPermUserId}/permissions`,
                    {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            permissions: this.userPermissions,
                        }),
                    }
                );

                if (!resp.ok) {
                    const data = await resp.json().catch(() => null);
                    throw new Error(data?.detail || 'Failed to save permissions');
                }

                this.successMessage = 'Permissions updated successfully';
                setTimeout(() => { this.successMessage = null; }, 4000);
            } catch (err) {
                this.error = err.message || 'Failed to save permissions';
            } finally {
                this.submitting = false;
            }
        },

        /* ================================================================== */
        /* Audit Tab                                                           */
        /* ================================================================== */

        /**
         * Load tenant-scoped audit log entries with server-side pagination,
         * search, and date filtering.
         * @returns {Promise<void>}
         */
        async loadAuditLogs() {
            this.auditLoading = true;
            this.error = null;
            this.successMessage = null;

            try {
                const params = new URLSearchParams();
                params.set('page', String(this.auditPage));
                params.set('per_page', String(this.auditPerPage));

                if (this.auditSearch.trim()) {
                    params.set('search', this.auditSearch.trim());
                }
                if (this.auditDateFrom) {
                    params.set('date_from', this.auditDateFrom);
                }
                if (this.auditDateTo) {
                    params.set('date_to', this.auditDateTo);
                }

                const resp = await authFetch(`/api/audit-logs?${params.toString()}`);
                if (!resp.ok) {
                    const data = await resp.json().catch(() => null);
                    throw new Error(data?.detail || `Failed to load audit logs (${resp.status})`);
                }

                const data = await resp.json();
                this.auditLogs = data.items || [];
                this.auditTotal = data.total || 0;
                this.auditPage = data.page || 1;
                this.auditTotalPages = data.pages || 0;
            } catch (err) {
                this.error = err.message || 'Failed to load audit logs';
            } finally {
                this.auditLoading = false;
            }
        },

        /* ================================================================== */
        /* Notifications Tab                                                   */
        /* ================================================================== */

        /**
         * Load organisation notification preferences from the company/settings API.
         * Falls back to defaults if no preferences have been saved yet.
         * @returns {Promise<void>}
         */
        async loadNotificationPrefs() {
            this.loading = true;
            try {
                const resp = await authFetch('/api/company');
                if (!resp.ok) throw new Error(`Failed to load company (${resp.status})`);
                const data = await resp.json();
                const prefs = data.notification_preferences || {};
                this.notifPrefs = {
                    reminder_24h: prefs.reminder_24h !== false,
                    reminder_1h: prefs.reminder_1h !== false,
                    default_whatsapp: prefs.default_whatsapp || false,
                    default_email: prefs.default_email || false,
                    notify_on_the_way: prefs.notify_on_the_way || false,
                    notify_completed: prefs.notify_completed || false,
                };
            } catch (err) {
                this.error = err.message || 'Failed to load notification preferences';
            } finally {
                this.loading = false;
            }
        },

        /**
         * Persist organisation notification preferences.
         * Debounced to avoid rapid-fire saves on quick checkbox toggles.
         */
        saveNotifPrefs() {
            if (this._notifSaveTimer) clearTimeout(this._notifSaveTimer);
            this._notifSaveTimer = setTimeout(async () => {
                try {
                    const resp = await authFetch('/api/company', {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            notification_preferences: { ...this.notifPrefs },
                        }),
                    });
                    if (!resp.ok) throw new Error('Failed to save notification preferences');
                    this.notifPrefsSaved = true;
                    setTimeout(() => { this.notifPrefsSaved = false; }, 2000);
                } catch (err) {
                    this.error = err.message || 'Failed to save notification preferences';
                }
            }, 400);
        },
    };
}
