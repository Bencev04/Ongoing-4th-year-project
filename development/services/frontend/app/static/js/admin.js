/**
 * Alpine.js application for the admin portal.
 *
 * Handles organization CRUD, user listing, audit log viewing,
 * platform settings, and user impersonation.
 *
 * @returns {Object} Alpine.js component data
 */
function adminApp() {
    return {
        /** @type {boolean} Whether the current user lacks superadmin access */
        accessDenied: false,
        /** @type {string} Active tab identifier */
        activeTab: 'organizations',
        /** @type {boolean} Loading state */
        loading: true,
        /** @type {boolean} Whether a mutation is in flight (prevents double-submit) */
        submitting: false,
        /** @type {string|null} Error message */
        error: null,
        /** @type {string|null} Success message */
        successMessage: null,

        /** @type {Array<Object>} Organizations list */
        organizations: [],
        /** @type {Array<Object>} Users list (cross-tenant) */
        users: [],
        /** @type {Array<Object>} Audit log entries */
        auditLogs: [],
        /** @type {string} Search query for audit logs */
        auditSearch: '',
        /** @type {string} Filter by action type */
        auditActionFilter: '',
        /** @type {string} Filter by resource type */
        auditResourceFilter: '',
        /** @type {number|null} Currently expanded log entry ID */
        expandedLogId: null,
        /** @type {Array<Object>} Platform settings */
        platformSettings: [],

        /** @type {string} Phone number for WhatsApp test */
        testWhatsAppNumber: '',
        /** @type {boolean} Whether a WhatsApp test is in flight */
        testingWhatsApp: false,
        /** @type {string|null} 'success' or 'error' after test */
        testWhatsAppResult: null,
        /** @type {string|null} Error detail from failed test */
        testWhatsAppError: null,

        /** @type {string} Email address for email test */
        testEmailAddress: '',
        /** @type {boolean} Whether an email test is in flight */
        testingEmail: false,
        /** @type {string|null} 'success' or 'error' after test */
        testEmailResult: null,
        /** @type {string|null} Error detail from failed email test */
        testEmailError: null,

        /** @type {boolean} Create org modal visibility */
        showCreateOrgModal: false,
        /** @type {Object} New organization form data */
        newOrg: {
            name: '',
            slug: '',
            billing_email: '',
            billing_plan: 'free',
            max_users: 50,
            max_customers: 500,
        },

        /** @type {boolean} Reset password modal visibility */
        showResetPasswordModal: false,
        /** @type {boolean} Submitting password reset */
        submittingReset: false,
        /** @type {Object|null} User whose password is being reset */
        resetPasswordUser: null,
        /** @type {Object} Reset password form data */
        resetPasswordForm: {
            newPassword: '',
            confirmPassword: '',
        },

        /** @type {boolean} Org detail modal visibility */
        showOrgDetailModal: false,
        /** @type {Object|null} Loaded organization detail */
        orgDetail: null,
        /** @type {boolean} Saving org notification settings */
        savingOrgNotif: false,
        /** @type {Object} Editable org fields (plan, limits) */
        orgEdit: {
            billing_plan: 'free',
            max_users: 50,
            max_customers: 500,
        },
        /** @type {Object} Editable notification overrides for the selected org */
        orgNotif: {
            use_custom_smtp: false,
            smtp: { host: '', port: 587, username: '', password: '', from_email: '', from_name: '', use_tls: false },
            use_custom_whatsapp: false,
            whatsapp: { account_sid: '', auth_token: '', phone_number: '' },
        },

        /** @type {boolean} Reason modal visibility */
        reasonModalOpen: false,
        /** @type {string} Reason modal title */
        reasonModalTitle: '',
        /** @type {string} Reason modal helper text */
        reasonModalDescription: '',
        /** @type {string} Reason input content */
        reasonText: '',
        /** @type {(function(string): Promise<void>|void)|null} Callback for reason submission */
        reasonCallback: null,

        /**
         * Initialise the admin app — check role, load orgs.
         * @returns {Promise<void>}
         */
        async init() {
            // Reuse the shared auth context loader so boosted navigation
            // does not fan out multiple /api/auth/me requests.
            try {
                const data = await getAuthContext();
                if (!data) {
                    this.accessDenied = true;
                    this.loading = false;
                    return;
                }
                if (data.role !== 'superadmin') {
                    this.accessDenied = true;
                    this.loading = false;
                    return;
                }
            } catch (e) {
                this.accessDenied = true;
                this.loading = false;
                return;
            }

            await this.loadOrganizations();
        },

        /**
         * Load organizations from the admin API.
         * @returns {Promise<void>}
         */
        async loadOrganizations() {
            this.loading = true;
            this.error = null;
            this.successMessage = null;
            try {
                const resp = await authFetch('/api/admin/organizations');
                if (!resp.ok) throw new Error(`Failed to load organizations (${resp.status})`);
                const data = await resp.json();
                this.organizations = data.items || [];
            } catch (err) {
                this.error = err.message || 'Failed to load organizations';
            } finally {
                this.loading = false;
            }
        },

        /**
         * Load users from the admin API.
         * @returns {Promise<void>}
         */
        async loadUsers() {
            this.loading = true;
            this.error = null;
            this.successMessage = null;
            try {
                const resp = await authFetch('/api/admin/users');
                if (!resp.ok) throw new Error(`Failed to load users (${resp.status})`);
                const data = await resp.json();
                this.users = data.items || [];
            } catch (err) {
                this.error = err.message || 'Failed to load users';
            } finally {
                this.loading = false;
            }
        },

        /**
         * Load audit logs from the admin API.
         * @returns {Promise<void>}
         */
        async loadAuditLogs() {
            this.loading = true;
            this.error = null;
            this.successMessage = null;
            this.expandedLogId = null;
            try {
                const resp = await authFetch('/api/admin/audit-logs?per_page=100');
                if (!resp.ok) throw new Error(`Failed to load audit logs (${resp.status})`);
                const data = await resp.json();
                this.auditLogs = data.items || [];
            } catch (err) {
                this.error = err.message || 'Failed to load audit logs';
            } finally {
                this.loading = false;
            }
        },

        /**
         * Unique action values from loaded audit logs for the filter dropdown.
         * @returns {Array<string>}
         */
        get auditActionOptions() {
            return [...new Set(this.auditLogs.map(l => l.action).filter(Boolean))].sort();
        },

        /**
         * Unique resource_type values from loaded audit logs for the filter dropdown.
         * @returns {Array<string>}
         */
        get auditResourceOptions() {
            return [...new Set(this.auditLogs.map(l => l.resource_type).filter(Boolean))].sort();
        },

        /**
         * Audit logs filtered by search text and dropdown filters.
         * Searches across actor_email, action, resource_type, resource_id, and details.
         * @returns {Array<Object>}
         */
        get filteredAuditLogs() {
            let logs = this.auditLogs;

            if (this.auditActionFilter) {
                logs = logs.filter(l => l.action === this.auditActionFilter);
            }
            if (this.auditResourceFilter) {
                logs = logs.filter(l => l.resource_type === this.auditResourceFilter);
            }
            if (this.auditSearch) {
                const q = this.auditSearch.toLowerCase();
                logs = logs.filter(l => {
                    const haystack = [
                        l.actor_email || '',
                        l.actor_role || '',
                        l.action || '',
                        l.resource_type || '',
                        l.resource_id ? String(l.resource_id) : '',
                        l.details ? JSON.stringify(l.details) : '',
                        l.ip_address || '',
                    ].join(' ').toLowerCase();
                    return haystack.includes(q);
                });
            }

            return logs;
        },

        /**
         * Load platform settings from the admin API.
         * @returns {Promise<void>}
         */
        async loadSettings(silent = false) {
            if (!silent) {
                this.loading = true;
                this.error = null;
                this.successMessage = null;
            }
            try {
                const resp = await authFetch('/api/admin/settings');
                if (!resp.ok) throw new Error(`Failed to load settings (${resp.status})`);
                const data = await resp.json();
                this.platformSettings = data.items || [];
            } catch (err) {
                this.error = err.message || 'Failed to load settings';
            } finally {
                if (!silent) this.loading = false;
            }
        },

        /**
         * Get a setting's value by key and property path.
         * @param {string} key - Setting key (e.g., 'maintenance_mode')
         * @param {string} prop - Property within the JSON value (e.g., 'enabled')
         * @returns {*} The value or null
         */
        getSettingValue(key, prop) {
            const setting = this.platformSettings.find(s => s.key === key);
            if (!setting || !setting.value) return null;
            try {
                const parsed = typeof setting.value === 'string'
                    ? JSON.parse(setting.value)
                    : setting.value;
                return parsed[prop] ?? null;
            } catch {
                return null;
            }
        },

        /**
         * Get a setting's description.
         * @param {string} key - Setting key
         * @returns {string} Description or empty string
         */
        getSettingDescription(key) {
            const setting = this.platformSettings.find(s => s.key === key);
            return setting?.description || '';
        },

        /**
         * Get who last updated a setting.
         * @param {string} key - Setting key
         * @returns {number|null} User ID or null
         */
        getSettingUpdatedBy(key) {
            const setting = this.platformSettings.find(s => s.key === key);
            return setting?.updated_by || null;
        },

        /**
         * Toggle maintenance mode on/off.
         * @returns {Promise<void>}
         */
        async toggleMaintenanceMode() {
            const currentValue = this.getSettingValue('maintenance_mode', 'enabled');
            const newValue = !currentValue;
            try {
                const resp = await authFetch('/api/admin/settings/maintenance_mode', {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ value: { enabled: newValue } }),
                });
                if (!resp.ok) throw new Error('Failed to update maintenance mode');
                await this.loadSettings(true);
            } catch (err) {
                this.error = err.message || 'Failed to toggle maintenance mode';
            }
        },

        /**
         * Toggle WhatsApp Tier 2 (automated messaging) on/off.
         * @returns {Promise<void>}
         */
        async toggleWhatsAppTier2() {
            const current = this.getSettingValue('whatsapp.tier2_enabled', 'enabled');
            try {
                const resp = await authFetch('/api/admin/settings/whatsapp.tier2_enabled', {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ value: { enabled: !current } }),
                });
                if (!resp.ok) throw new Error('Failed to update WhatsApp Tier 2 setting');
                await this.loadSettings(true);
            } catch (err) {
                this.error = err.message || 'Failed to toggle WhatsApp Tier 2';
            }
        },

        /**
         * Send a test email to verify SMTP configuration.
         * @returns {Promise<void>}
         */
        async testEmailConfig() {
            if (this.testingEmail || !this.testEmailAddress.trim()) return;
            this.testingEmail = true;
            this.testEmailResult = null;
            this.testEmailError = null;
            try {
                const resp = await authFetch('/api/notifications/send-test', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        channel: 'email',
                        recipient: this.testEmailAddress.trim(),
                    }),
                });
                if (!resp.ok) {
                    const data = await resp.json().catch(() => null);
                    throw new Error(data?.detail || `Test failed (${resp.status})`);
                }
                const result = await resp.json();
                if (!result.success) {
                    throw new Error(result.error || 'Email send failed — check SMTP settings');
                }
                this.testEmailResult = 'success';
            } catch (err) {
                this.testEmailResult = 'error';
                this.testEmailError = err.message || 'Test failed — check SMTP configuration';
            } finally {
                this.testingEmail = false;
            }
        },

        /**
         * Send a test WhatsApp message to verify Twilio configuration.
         * @returns {Promise<void>}
         */
        async testWhatsAppConfig() {
            if (this.testingWhatsApp || !this.testWhatsAppNumber.trim()) return;
            this.testingWhatsApp = true;
            this.testWhatsAppResult = null;
            this.testWhatsAppError = null;
            try {
                const resp = await authFetch('/api/notifications/send-test', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        channel: 'whatsapp',
                        recipient: this.testWhatsAppNumber.trim(),
                    }),
                });
                if (!resp.ok) {
                    const data = await resp.json().catch(() => null);
                    throw new Error(data?.detail || `Test failed (${resp.status})`);
                }
                const result = await resp.json();
                if (!result.success) {
                    throw new Error(result.error || 'WhatsApp send failed — check Twilio credentials');
                }
                this.testWhatsAppResult = 'success';
            } catch (err) {
                this.testWhatsAppResult = 'error';
                this.testWhatsAppError = err.message || 'Test failed — check Twilio credentials';
            } finally {
                this.testingWhatsApp = false;
            }
        },

        /**
         * Update a setting value.
         * @param {string} key - Setting key
         * @param {Object} value - New value object
         * @param {HTMLElement} input - Input element (to restore on error)
         * @returns {Promise<void>}
         */
        async updateSetting(key, value, input) {
            const originalValue = input.value;
            try {
                const resp = await authFetch(`/api/admin/settings/${key}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ value }),
                });
                if (!resp.ok) throw new Error(`Failed to update ${key}`);
                await this.loadSettings(true); // Silent reload — no loading flash
            } catch (err) {
                this.error = err.message || `Failed to update ${key}`;
                input.value = originalValue; // Restore original on error
            }
        },

        /** Open the create organization modal. */
        openCreateOrgModal() {
            this.newOrg = {
                name: '',
                slug: '',
                billing_email: '',
                billing_plan: 'free',
                max_users: 50,
                max_customers: 500,
            };
            this.showCreateOrgModal = true;
        },

        /**
         * Create a new organization.
         * @returns {Promise<void>}
         */
        async createOrganization() {
            if (this.submitting) return;
            this.submitting = true;
            this.error = null;
            try {
                const resp = await authFetch('/api/admin/organizations', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(this.newOrg),
                });
                if (!resp.ok) {
                    const data = await resp.json().catch(() => null);
                    throw new Error(data?.detail || `Failed to create organization (${resp.status})`);
                }
                this.showCreateOrgModal = false;
                await this.loadOrganizations();
            } catch (err) {
                this.error = err.message;
            } finally {
                this.submitting = false;
            }
        },

        /**
         * Suspend an organization.
         * @param {number} orgId - Organization ID
         * @returns {Promise<void>}
         */
        async suspendOrg(orgId) {
            if (this.submitting) return;
            this.openReasonModal(
                'Suspend Organization',
                'Reason for suspension (required for audit trail)',
                async (reason) => {
                    if (this.submitting) return;
                    this.submitting = true;
                    this.error = null;
                    this.successMessage = null;
                    try {
                        const resp = await authFetch(`/api/admin/organizations/${orgId}/suspend`, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ reason }),
                        });
                        if (!resp.ok) throw new Error('Failed to suspend organization');
                        await this.loadOrganizations();
                        this.successMessage = 'Organization suspended successfully.';
                    } catch (err) {
                        this.error = err.message;
                    } finally {
                        this.submitting = false;
                    }
                }
            );
        },

        /**
         * Reactivate a suspended organization.
         * @param {number} orgId - Organization ID
         * @returns {Promise<void>}
         */
        async unsuspendOrg(orgId) {
            if (this.submitting) return;
            this.submitting = true;
            this.successMessage = null;
            try {
                const resp = await authFetch(`/api/admin/organizations/${orgId}/unsuspend`, {
                    method: 'POST',
                });
                if (!resp.ok) throw new Error('Failed to reactivate organization');
                await this.loadOrganizations();
                this.successMessage = 'Organization reactivated successfully.';
            } catch (err) {
                this.error = err.message;
            } finally {
                this.submitting = false;
            }
        },

        /**
         * Open the org detail modal with notification settings.
         * @param {number} orgId - Organization ID
         * @returns {Promise<void>}
         */
        async viewOrgDetail(orgId) {
            this.error = null;
            try {
                const resp = await authFetch(`/api/admin/organizations/${orgId}`);
                if (!resp.ok) throw new Error(`Failed to load organization (${resp.status})`);
                this.orgDetail = await resp.json();

                // Populate editable org fields
                this.orgEdit = {
                    billing_plan: this.orgDetail.billing_plan || 'free',
                    max_users: this.orgDetail.max_users || 50,
                    max_customers: this.orgDetail.max_customers || 500,
                };

                // Populate orgNotif from saved notification_settings or defaults
                const ns = this.orgDetail.notification_settings || {};
                this.orgNotif = {
                    use_custom_smtp: ns.use_custom_smtp || false,
                    smtp: {
                        host: ns.smtp?.host || '',
                        port: ns.smtp?.port || 587,
                        username: ns.smtp?.username || '',
                        password: ns.smtp?.password || '',
                        from_email: ns.smtp?.from_email || '',
                        from_name: ns.smtp?.from_name || '',
                        use_tls: ns.smtp?.use_tls || false,
                    },
                    use_custom_whatsapp: ns.use_custom_whatsapp || false,
                    whatsapp: {
                        account_sid: ns.whatsapp?.account_sid || '',
                        auth_token: ns.whatsapp?.auth_token || '',
                        phone_number: ns.whatsapp?.phone_number || '',
                    },
                };

                this.showOrgDetailModal = true;
            } catch (err) {
                this.error = err.message || 'Failed to load organization details';
            }
        },

        /**
         * Save all org changes (plan, limits, and notification settings).
         * @returns {Promise<void>}
         */
        async saveOrgDetails() {
            if (this.savingOrgNotif || !this.orgDetail) return;
            this.savingOrgNotif = true;
            this.error = null;
            try {
                const payload = {
                    billing_plan: this.orgEdit.billing_plan,
                    max_users: this.orgEdit.max_users,
                    max_customers: this.orgEdit.max_customers,
                    notification_settings: {
                        use_custom_smtp: this.orgNotif.use_custom_smtp,
                        smtp: this.orgNotif.use_custom_smtp ? { ...this.orgNotif.smtp } : {},
                        use_custom_whatsapp: this.orgNotif.use_custom_whatsapp,
                        whatsapp: this.orgNotif.use_custom_whatsapp ? { ...this.orgNotif.whatsapp } : {},
                    },
                };

                const resp = await authFetch(`/api/admin/organizations/${this.orgDetail.id}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload),
                });
                if (!resp.ok) {
                    const data = await resp.json().catch(() => null);
                    throw new Error(data?.detail || `Failed to save (${resp.status})`);
                }

                this.showOrgDetailModal = false;
                this.successMessage = `Organization "${this.orgDetail.name}" updated successfully.`;
                await this.loadOrganizations();
                setTimeout(() => { if (this.successMessage) this.successMessage = null; }, 3000);
            } catch (err) {
                this.error = err.message || 'Failed to save organization settings';
            } finally {
                this.savingOrgNotif = false;
            }
        },

        /**
         * Impersonate a user via the auth service.
         *
         * Creates a shadow token and stores it, replacing
         * the current session temporarily.
         *
         * @param {number} userId - ID of the user to impersonate
         * @returns {Promise<void>}
         */
        async impersonateUser(userId) {
            if (this.submitting) return;
            this.openReasonModal(
                'Impersonate User',
                'Reason for impersonation (required for audit trail)',
                async (reason) => {
                    if (this.submitting) return;
                    this.submitting = true;
                    this.error = null;
                    this.successMessage = null;
                    try {
                        const resp = await authFetch('/api/auth/impersonate', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({
                                target_user_id: userId,
                                reason,
                            }),
                        });

                        if (!resp.ok) {
                            const data = await resp.json().catch(() => null);
                            throw new Error(data?.detail || 'Impersonation failed');
                        }

                        // Proxy sets impersonation auth cookies server-side.
                        await resp.json().catch(() => null);

                        // Redirect to calendar as the impersonated user
                        window.location.href = '/calendar';
                    } catch (err) {
                        this.error = err.message;
                    } finally {
                        this.submitting = false;
                    }
                }
            );
        },

        /**
         * Update a user's role via the admin API.
         * @param {number} userId - User ID
         * @param {string} newRole - New role value
         * @param {Event} event - Change event (to revert on failure)
         * @returns {Promise<void>}
         */
        async updateUserRole(userId, newRole, event) {
            this.error = null;
            this.successMessage = null;
            try {
                const resp = await authFetch(`/api/admin/users/${userId}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ role: newRole }),
                });
                if (!resp.ok) {
                    const data = await resp.json().catch(() => null);
                    throw new Error(data?.detail || `Failed to update role (${resp.status})`);
                }
                this.successMessage = `Role updated to "${newRole}" successfully.`;
                setTimeout(() => { if (this.successMessage) this.successMessage = null; }, 3000);
            } catch (err) {
                this.error = err.message || 'Failed to update user role';
                // Revert the dropdown — reload users to get the real state
                await this.loadUsers();
            }
        },

        /**
         * Open a reusable reason modal.
         *
         * @param {string} title - Modal heading.
         * @param {string} description - Helper text under the heading.
         * @param {(function(string): Promise<void>|void)} callback - Callback to run with reason text.
         * @returns {void}
         */
        openReasonModal(title, description, callback) {
            this.reasonModalTitle = title;
            this.reasonModalDescription = description;
            this.reasonText = '';
            this.reasonCallback = callback;
            this.reasonModalOpen = true;
        },

        /**
         * Close reason modal and clear callback state.
         *
         * @returns {void}
         */
        closeReasonModal() {
            this.reasonModalOpen = false;
            this.reasonText = '';
            this.reasonModalTitle = '';
            this.reasonModalDescription = '';
            this.reasonCallback = null;
        },

        /**
         * Submit reason modal with required non-empty text.
         *
         * @returns {Promise<void>}
         */
        async submitReasonModal() {
            const reason = this.reasonText.trim();
            if (!reason) {
                this.error = 'A reason is required.';
                return;
            }

            const callback = this.reasonCallback;
            this.closeReasonModal();
            this.error = null;

            if (typeof callback === 'function') {
                await callback(reason);
            }
        },

        /**
         * Open the reset password modal for a user.
         *
         * @param {Object} user - User object
         * @returns {void}
         */
        openResetPasswordModal(user) {
            this.resetPasswordUser = user;
            this.resetPasswordForm = {
                newPassword: '',
                confirmPassword: '',
            };
            this.showResetPasswordModal = true;
        },

        /**
         * Reset a user's password via the auth service.
         *
         * @returns {Promise<void>}
         */
        async resetUserPassword() {
            // Validate passwords match
            if (this.resetPasswordForm.newPassword !== this.resetPasswordForm.confirmPassword) {
                this.error = 'Passwords do not match';
                return;
            }

            // Validate minimum length
            if (this.resetPasswordForm.newPassword.length < 8) {
                this.error = 'Password must be at least 8 characters';
                return;
            }

            if (this.submittingReset) return;
            this.submittingReset = true;
            this.error = null;
            this.successMessage = null;

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

                // Success!
                this.showResetPasswordModal = false;
                this.error = null;

                // Show success message briefly
                const successText = `Password reset successfully for ${this.resetPasswordUser.first_name} ${this.resetPasswordUser.last_name}`;
                this.successMessage = successText;
                setTimeout(() => {
                    if (this.successMessage === successText) {
                        this.successMessage = null;
                    }
                }, 3000);
            } catch (err) {
                this.error = err.message;
            } finally {
                this.submittingReset = false;
            }
        },
    };
}
