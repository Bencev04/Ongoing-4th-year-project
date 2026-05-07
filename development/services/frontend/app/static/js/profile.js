/**
 * Alpine.js component for the profile page.
 *
 * Loads current user info from the auth service and provides
 * a password-change form. Must be loaded as a deferred script
 * BEFORE Alpine.js initialises (see base.html).
 *
 * @returns {Object} Alpine.js component data
 */
function profileApp() {
    return {
        /** @type {boolean} */
        loading: true,
        /** @type {boolean} */
        submitting: false,
        /** @type {string|null} */
        error: null,
        /** @type {string|null} */
        successMessage: null,
        /** @type {Object} */
        userInfo: {},
        /** @type {{currentPassword: string, newPassword: string, confirmPassword: string}} */
        passwordForm: {
            currentPassword: '',
            newPassword: '',
            confirmPassword: ''
        },

        /* -- GDPR data properties ---------------------------------------- */
        /** @type {boolean} */
        exportingData: false,
        /** @type {boolean} */
        anonymizeLoading: false,
        /** @type {string|null} */
        anonymizeScheduledAt: null,
        /** @type {boolean} */
        showDeleteConfirm: false,

        /**
         * Load current user information from the auth service.
         * @returns {Promise<void>}
         */
        async loadUserInfo() {
            this.loading = true;
            this.error = null;
            try {
                const resp = await authFetch('/api/auth/me');
                if (!resp.ok) {
                    throw new Error('Failed to load user information');
                }
                this.userInfo = await resp.json();

                // Load GDPR consent / anonymization status
                const consentResp = await authFetch('/api/users/me/consent-status');
                if (consentResp.ok) {
                    const consent = await consentResp.json();
                    this.anonymizeScheduledAt = consent.anonymize_scheduled_at || null;
                }
            } catch (err) {
                console.error('Failed to load user info:', err);
                this.error = err.message || 'Failed to load user information';
            } finally {
                this.loading = false;
            }
        },

        /**
         * Change the user's password.
         * @returns {Promise<void>}
         */
        async changePassword() {
            this.error = null;
            this.successMessage = null;

            if (this.passwordForm.newPassword !== this.passwordForm.confirmPassword) {
                this.error = 'New passwords do not match';
                return;
            }

            if (this.passwordForm.newPassword.length < 8) {
                this.error = 'Password must be at least 8 characters';
                return;
            }

            if (this.passwordForm.currentPassword === this.passwordForm.newPassword) {
                this.error = 'New password must be different from current password';
                return;
            }

            this.submitting = true;

            try {
                const resp = await authFetch('/api/auth/change-password', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        current_password: this.passwordForm.currentPassword,
                        new_password: this.passwordForm.newPassword
                    })
                });

                if (resp.status === 401) {
                    throw new Error('Current password is incorrect');
                }

                if (!resp.ok) {
                    const data = await resp.json().catch(() => null);
                    throw new Error(data?.detail || `Failed to change password (${resp.status})`);
                }

                this.successMessage = 'Password changed successfully';
                this.passwordForm = {
                    currentPassword: '',
                    newPassword: '',
                    confirmPassword: ''
                };

                setTimeout(() => {
                    this.successMessage = null;
                }, 5000);

            } catch (err) {
                console.error('Password change error:', err);
                this.error = err.message || 'Failed to change password';
            } finally {
                this.submitting = false;
            }
        },

        /* -- GDPR methods ------------------------------------------------ */

        /**
         * Download all personal data as a JSON file (GDPR Article 15/20).
         * @returns {Promise<void>}
         */
        async downloadMyData() {
            this.exportingData = true;
            this.error = null;
            try {
                const resp = await authFetch('/api/users/me/export');
                if (!resp.ok) throw new Error('Failed to export data');
                const data = await resp.json();
                const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `my-data-export-${new Date().toISOString().slice(0, 10)}.json`;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                URL.revokeObjectURL(url);
                this.successMessage = 'Data exported successfully';
                setTimeout(() => { this.successMessage = null; }, 5000);
            } catch (err) {
                this.error = err.message || 'Failed to export data';
            } finally {
                this.exportingData = false;
            }
        },

        /**
         * Schedule account anonymization (72-hour grace period).
         * @returns {Promise<void>}
         */
        async scheduleAnonymization() {
            this.anonymizeLoading = true;
            this.error = null;
            try {
                const resp = await authFetch('/api/users/me/anonymize/schedule', { method: 'POST' });
                if (!resp.ok) throw new Error('Failed to schedule account deletion');
                const data = await resp.json();
                this.anonymizeScheduledAt = data.anonymize_scheduled_at;
                this.showDeleteConfirm = false;
                this.successMessage = 'Account deletion scheduled. You have 72 hours to cancel.';
                setTimeout(() => { this.successMessage = null; }, 8000);
            } catch (err) {
                this.error = err.message || 'Failed to schedule account deletion';
            } finally {
                this.anonymizeLoading = false;
            }
        },

        /**
         * Cancel a pending account anonymization.
         * @returns {Promise<void>}
         */
        async cancelAnonymization() {
            this.anonymizeLoading = true;
            this.error = null;
            try {
                const resp = await authFetch('/api/users/me/anonymize/cancel', { method: 'POST' });
                if (!resp.ok) throw new Error('Failed to cancel account deletion');
                this.anonymizeScheduledAt = null;
                this.successMessage = 'Account deletion cancelled.';
                setTimeout(() => { this.successMessage = null; }, 5000);
            } catch (err) {
                this.error = err.message || 'Failed to cancel account deletion';
            } finally {
                this.anonymizeLoading = false;
            }
        }
    };
}
