/**
 * calendarApp — Alpine.js component for the calendar page.
 *
 * Responsibilities:
 *   • Track the currently selected date.
 *   • Support drag-and-drop rescheduling of job cards.
 *   • Trigger grid refresh after job creation / reschedule.
 *
 * Server-side rendering populates events into the grid on page
 * load and on every HTMX navigation swap.  This component only
 * handles interactive operations (drag-drop, modals).
 *
 * @returns {object} Alpine.js reactive data + methods.
 */
function calendarApp() {
    return {
        /* ── Reactive state ─────────────────────────────────────── */

        /** @type {string|null} Currently selected date (YYYY-MM-DD). */
        selectedDate: null,

        /** @type {number|null} ID of the job being dragged. */
        draggedJob: null,

        /** @type {Array<string>} Selected employee IDs for filtering (empty = all). */
        filterEmployeeIds: [],

        /** @type {Array<string>} Selected customer IDs for filtering (empty = all). */
        filterCustomerIds: [],

        /** @type {string} Search text for employee dropdown. */
        employeeSearch: '',

        /** @type {string} Search text for customer dropdown. */
        customerSearch: '',

        /** @type {boolean} Whether the employee dropdown is open. */
        employeeDropdownOpen: false,

        /** @type {boolean} Whether the customer dropdown is open. */
        customerDropdownOpen: false,
        /** @type {boolean} Prevent duplicate global listener registration. */
        _listenersAttached: false,

        // ── Permission flags ────────────────────────────────────
        /** @type {boolean} Whether the user can create jobs */
        canCreateJob: false,
        /** @type {boolean} Whether the user can schedule / reschedule jobs */
        canScheduleJob: false,
        /** @type {boolean} Whether the user can edit jobs */
        canEditJob: false,

        /* ── Lifecycle ─────────────────────────────────────────── */

        /**
         * Called once when the component mounts.
         * Redirects superadmin to the admin portal (no tenant context).
         * Loads permission flags, then listens for job-creation events.
         */
        async init() {
            // Superadmin has no tenant — redirect to admin portal.
            if (
                typeof getUserRole === 'function' &&
                await getUserRole() === 'superadmin'
            ) {
                window.location.href = '/admin';
                return;
            }

            // Load permission flags for UI gating
            if (typeof hasPermission === 'function') {
                const [create, schedule, edit] = await Promise.all([
                    hasPermission('jobs.create'),
                    hasPermission('jobs.schedule'),
                    hasPermission('jobs.edit'),
                ]);
                this.canCreateJob   = create;
                this.canScheduleJob = schedule;
                this.canEditJob     = edit;

                if (typeof updatePermissionStore === 'function') {
                    updatePermissionStore({
                        canCreateJob: create,
                        canScheduleJob: schedule,
                        canEditJob: edit,
                    });
                }
            }

            // Refresh calendar to ensure we show current user's data
            this.refreshCalendar();

            if (this._listenersAttached) return;
            console.log('Calendar initialized');

            // After a job is created or updated, refresh the visible grid.
            document.body.addEventListener('calendarUpdated', () => {
                this.refreshCalendar();
            });
            document.body.addEventListener('jobQueueUpdated', () => {
                this.refreshCalendar();
            });
            this._listenersAttached = true;
        },

        /* ── Calendar refresh ──────────────────────────────────── */

        /**
         * Trigger an HTMX re-fetch of the current calendar container.
         * Reads the year/month from hidden inputs placed by the
         * server-rendered grid partial.
         */
        refreshCalendar() {
            const yearEl = document.getElementById('current-year');
            const monthEl = document.getElementById('current-month');
            const viewEl = document.getElementById('current-view');
            const dayEl = document.getElementById('current-day');
            if (yearEl && monthEl) {
                const year = yearEl.value;
                const month = monthEl.value;
                const view = viewEl ? viewEl.value : 'month';
                const day = dayEl ? dayEl.value : '1';
                const params = new URLSearchParams({ year, month });
                if (this.filterEmployeeIds.length) params.set('employee_ids', this.filterEmployeeIds.join(','));
                if (this.filterCustomerIds.length) params.set('customer_ids', this.filterCustomerIds.join(','));

                let url;
                if (view === 'week') {
                    params.set('day', day);
                    url = `/calendar/week?${params.toString()}`;
                } else if (view === 'day') {
                    const dd = day.padStart(2, '0');
                    const mm = month.padStart(2, '0');
                    const yyyy = year.padStart(4, '0');
                    url = `/calendar/day-view/${yyyy}-${mm}-${dd}?${params.toString()}`;
                } else {
                    url = `/calendar/container?${params.toString()}`;
                }

                htmx.ajax('GET', url, '#calendar-container');
            }
        },

        /* ── UI actions ────────────────────────────────────────── */

        /**
         * Mark a day cell as selected.
         *
         * @param {string} date — Date string (YYYY-MM-DD).
         */
        selectDay(date) {
            this.selectedDate = date;
        },

        /* ── Drag-and-drop ─────────────────────────────────────── */

        /**
         * Begin dragging a job card.
         * Blocked when the user lacks the `jobs.schedule` permission.
         *
         * @param {DragEvent} event — Native drag event.
         * @param {number}    jobId — ID of the job being moved.
         */
        handleDragStart(event, jobId) {
            if (!this.canScheduleJob) {
                event.preventDefault();
                return;
            }
            this.draggedJob = jobId;
            event.dataTransfer.setData('text/plain', String(jobId));
            event.dataTransfer.effectAllowed = 'move';
        },

        /**
         * Reset drag state after drag operation ends.
         *
         * @param {DragEvent} _event - Native dragend event.
         */
        handleDragEnd(_event) {
            this.draggedJob = null;
        },

        /**
         * Handle a job card being dropped on a calendar day.
         * Blocked when the user lacks the `jobs.schedule` permission.
         *
         * If the job already has an assigned employee and time slot
         * it is scheduled directly via PATCH.  Otherwise the
         * quick-schedule modal is loaded so the user can fill in
         * the missing details before confirming.
         *
         * @param {DragEvent} event — Native drop event.
         * @param {string}    date  — Target date (YYYY-MM-DD).
         */
        async handleDrop(event, date) {
            event.preventDefault();
            if (!this.canScheduleJob) {
                this.draggedJob = null;
                return;
            }
            const jobId = event.dataTransfer.getData('text/plain');
            if (!jobId) {
                this.draggedJob = null;
                return;
            }

            console.log(`Drop: job ${jobId} → ${date}`);

            try {
                /* Fetch current job details to decide whether the
                   quick-schedule modal is needed. */
                const detailResp = await authFetch(`/api/jobs/${jobId}`);
                if (!detailResp.ok) {
                    if (window.showNotification) {
                        window.showNotification('Could not load job details', 'error');
                    }
                    this.draggedJob = null;
                    return;
                }

                const job = await detailResp.json();

                /* Determine if required scheduling fields are present.
                   A job needs a time range and (ideally) an employee
                   before being placed on the calendar.  If either is
                   missing we show the quick-schedule modal. */
                const hasEmployee = Boolean(job.assigned_to);
                const hasTime     = Boolean(job.start_time && job.end_time);

                if (hasEmployee && hasTime) {
                    /* All fields present — schedule directly to new date,
                       keeping the existing times. */
                    await this._scheduleDirectly(jobId, date, job);
                } else {
                    /* Open quick-schedule modal for user to fill gaps. */
                    const modalUrl =
                        `/calendar/quick-schedule-modal?job_id=${jobId}&date=${date}`;
                    htmx.ajax('GET', modalUrl, '#modal-container');
                }
            } catch (err) {
                console.error('handleDrop error:', err);
                if (window.showNotification) {
                    window.showNotification('Network error — please try again', 'error');
                }
            }

            this.draggedJob = null;
        },

        /**
         * Schedule a job directly via PATCH without opening a modal.
         * Used when the job already has all required fields filled.
         * Preserves the original time-of-day but moves to the new date.
         *
         * @param {string} jobId — Job ID.
         * @param {string} date  — Target date (YYYY-MM-DD).
         * @param {object} job   — Full job object from the API.
         */
        async _scheduleDirectly(jobId, date, job) {
            /* Extract existing time portions or fall back to defaults */
            let startTime = '09:00:00';
            let endTime   = '17:00:00';

            if (job.start_time) {
                const st = job.start_time.split('T');
                if (st.length > 1) startTime = st[1].substring(0, 8);
            }
            if (job.end_time) {
                const et = job.end_time.split('T');
                if (et.length > 1) endTime = et[1].substring(0, 8);
            }

            try {
                const response = await authFetch(`/api/jobs/${jobId}`, {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        start_time: `${date}T${startTime}`,
                        end_time:   `${date}T${endTime}`,
                        status:     'scheduled',
                    })
                });

                if (response.ok) {
                    if (window.showNotification) {
                        window.showNotification('Job scheduled successfully', 'success');
                    }
                    htmx.trigger(document.body, 'calendarUpdated');
                    htmx.trigger(document.body, 'jobQueueUpdated');
                } else {
                    const errData = await response.json().catch(() => ({}));
                    const msg = errData.detail || 'Failed to schedule job';
                    if (window.showNotification) {
                        window.showNotification(msg, 'error');
                    }
                }
            } catch (error) {
                console.error('_scheduleDirectly error:', error);
                if (window.showNotification) {
                    window.showNotification('Network error — please try again', 'error');
                }
            }
        },

        /**
         * Allow the day cell to accept a drop.
         *
         * @param {DragEvent} event — Native dragover event.
         */
        handleDragOver(event) {
            event.preventDefault();
            event.dataTransfer.dropEffect = 'move';
        }
    };
}
