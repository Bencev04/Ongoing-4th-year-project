/**
 * Map View page — Alpine.js component.
 *
 * Loads scheduled jobs from the calendar API, plots them as colour-coded
 * markers on a Google Map, and provides:
 *   - Date / status / employee filters (employee is server-side)
 *   - A collapsible "Job Tiles" panel listing all visible jobs
 *   - Route planning with tile → stop drag integration
 *   - Hover cross-highlighting between tiles and markers
 *
 * @file map-page.js
 */

/* global google, markerClusterer, authFetch */

// ── Raw (non-proxied) storage ───────────────────────────────────────────────
// Alpine.js wraps data properties in Proxy objects, which breaks Google Maps
// API calls like marker.map = null, clusterer.setMap(null), and — critically —
// passing the map to AdvancedMarkerElement / MarkerClusterer constructors
// (Google Maps uses identity checks / WeakMap internally which fail on Proxies).
// We keep raw references at module scope so all Google Maps calls use the
// real objects, not their Alpine wrappers.
/** @type {google.maps.Map|null} */
let _rawMap = null;
/** @type {Array<google.maps.marker.AdvancedMarkerElement|google.maps.Marker>} */
let _rawMarkers = [];
/** @type {Object|null} */
let _rawClusterer = null;
/** @type {Object<number, google.maps.marker.AdvancedMarkerElement|google.maps.Marker>} */
let _rawMarkerByJobId = {};
/** @type {Array<google.maps.marker.AdvancedMarkerElement|google.maps.Marker>} Numbered route stop markers. */
let _rawRouteMarkers = [];
/** @type {google.maps.places.Autocomplete|null} Autocomplete for the custom address input. */
let _routeAutocomplete = null;

// Status constants are now shared — defined in maps-utils.js:
// STATUS_COLOURS, STATUS_LABELS

/**
 * Alpine.js component for the Map View page.
 *
 * @returns {Object} Alpine data object.
 */
function mapViewApp() {
    /** @type {Date} */
    const today = new Date();
    const yyyy = today.getFullYear();
    const mm = String(today.getMonth() + 1).padStart(2, "0");

    // Default range: current month
    const monthStart = `${yyyy}-${mm}-01`;
    const lastDay = new Date(yyyy, today.getMonth() + 1, 0).getDate();
    const monthEnd = `${yyyy}-${mm}-${String(lastDay).padStart(2, "0")}`;

    return {
        // ── State ────────────────────────────────────────────────
        /** @type {google.maps.Map|null} */
        map: null,
        /** @type {Array<Object>} All jobs from the API (unfiltered). */
        allJobs: [],
        /** @type {Array<Object>} Jobs after status filter + geo check. */
        visibleJobs: [],
        /** @type {Array<Object>} Employee list for dropdown. */
        employees: [],
        /** @type {Array<google.maps.marker.AdvancedMarkerElement|google.maps.Marker>} */
        markers: [],
        /** @type {Object|null} MarkerClusterer instance. */
        clusterer: null,
        /** @type {google.maps.InfoWindow|null} */
        infoWindow: null,

        // Filters
        /** @type {boolean} When true, load all jobs regardless of date range. */
        showAllDates: true,
        startDate: monthStart,
        endDate: monthEnd,
        filterStatus: "",
        filterEmployee: "",
        loading: false,

        // Route planning
        routeMode: false,
        /** @type {Array<Object>} Ordered list of route stops. */
        routeStops: [],
        /** @type {Object|null} Calculated distance/duration info. */
        routeInfo: null,
        /** @type {google.maps.Polyline|null} */
        routePolyline: null,

        // Route custom locations
        /** @type {Object|null} Company address: { lat, lng, address }. Loaded once. */
        companyAddress: null,
        /** @type {string} Free-text in the custom address input. */
        customAddressInput: "",
        /** @type {Object|null} Resolved coords from autocomplete/geocode: { lat, lng, address }. */
        customAddressCoords: null,
        /** @type {Object|null} Route start location: { lat, lng, address }. */
        startLocation: null,
        /** @type {Object|null} Route end location: { lat, lng, address }. */
        endLocation: null,

        // ── Unscheduled jobs state ─────────────────────────────────
        /** @type {Array<Object>} Unscheduled jobs from the queue API. */
        unscheduledJobs: [],

        // ── Schedule modal state ─────────────────────────────────────
        /** @type {Object} Schedule-commit modal state. */
        scheduleModal: {
            open: false,
            employeeId: "",
            targetDate: "",
            stops: [],
            submitting: false,
            error: "",
            successCount: 0,
            failCount: 0,
            done: false,
        },

        // ── Tiles panel state ────────────────────────────────────
        /** @type {boolean} Whether the tiles panel is collapsed. */
        tilesCollapsed: false,
        /** @type {number|null} Job ID currently hovered (tile or marker). */
        hoveredJobId: null,
        /**
         * Lookup: job ID → marker reference.
         * Populated during _renderMarkers() so hover/cross-highlight
         * can bounce a marker without a full re-render.
         * @type {Object<number, google.maps.marker.AdvancedMarkerElement|google.maps.Marker>}
         */
        markerByJobId: {},

        // ── Lifecycle ────────────────────────────────────────────

        /**
         * Initialise the map and load data.
         * Waits for the Maps API to be ready before rendering.
         *
         * @returns {void}
         */
        init() {
            if (window.mapsReady) {
                this._setup();
            } else {
                document.addEventListener("mapsReady", () => this._setup(), { once: true });
            }
        },

        /**
         * Internal setup — called once the Maps JS API is ready.
         *
         * @returns {void}
         */
        _setup() {
            const canvas = document.getElementById("map-canvas");
            const mapId = canvas ? canvas.dataset.mapId : "";

            /** @type {google.maps.MapOptions} */
            const mapOpts = {
                center: { lat: 53.35, lng: -6.26 },
                zoom: 8,
                mapTypeControl: true,
                streetViewControl: false,
                fullscreenControl: true,
                gestureHandling: 'greedy',
                clickableIcons: false,
            };
            if (mapId) mapOpts.mapId = mapId;

            // Store the raw Map reference BEFORE Alpine proxies it
            _rawMap = new google.maps.Map(canvas, mapOpts);
            this.map = _rawMap;

            this.infoWindow = new google.maps.InfoWindow();

            // Re-render markers if the map rendering type changes
            // (e.g. UNINITIALIZED → VECTOR after tiles load).
            _rawMap.addListener("renderingtype_changed", () => {
                if (this.markers.length > 0) this._renderMarkers();
            });

            // Load employees, jobs, and company address in parallel
            Promise.all([this.loadEmployees(), this.loadJobs(), this.loadCompanyAddress()]);
        },

        // ── Data loading ─────────────────────────────────────────

        /**
         * Fetch employees for the filter dropdown.
         *
         * @returns {Promise<void>}
         */
        async loadEmployees() {
            try {
                const resp = await authFetch("/api/employees/");
                if (resp.ok) {
                    const data = await resp.json();
                    this.employees = Array.isArray(data) ? data : (data.items || []);
                }
            } catch (err) {
                console.debug("Map: failed to load employees", err);
            }
        },

        /**
         * Fetch jobs and render markers.
         *
         * When `showAllDates` is true, fetches all jobs from the jobs
         * list endpoint (no date restriction). Otherwise uses the
         * calendar API scoped to the selected date range.
         *
         * When an employee filter is active, the employee_id is sent
         * as a query param so the server returns only matching jobs.
         *
         * @returns {Promise<void>}
         */
        async loadJobs() {
            this.loading = true;

            try {
                let url;

                if (this.showAllDates) {
                    // Fetch ALL jobs (paginated list endpoint, max 1000)
                    url = `/api/jobs/?limit=1000`;
                    if (this.filterEmployee) {
                        url += `&assigned_to=${encodeURIComponent(this.filterEmployee)}`;
                    }
                } else {
                    if (!this.startDate || !this.endDate) {
                        this.loading = false;
                        return;
                    }
                    // Calendar API with date range
                    url = `/api/jobs/calendar?start_date=${this.startDate}&end_date=${this.endDate}`;
                    if (this.filterEmployee) {
                        url += `&employee_id=${encodeURIComponent(this.filterEmployee)}`;
                    }
                }

                const resp = await authFetch(url);

                if (!resp.ok) {
                    console.error("Map: jobs API returned", resp.status);
                    this.allJobs = [];
                } else {
                    const data = await resp.json();

                    if (this.showAllDates) {
                        // List API returns {items: [...], total, ...}
                        this.allJobs = Array.isArray(data) ? data : (data.items || []);
                    } else {
                        // Calendar API returns day-grouped data:
                        // [{date, jobs: [...], total_jobs}, ...]
                        // Flatten into a single job list for the map.
                        const dayGroups = Array.isArray(data) ? data : (data.events || []);
                        const jobMap = new Map();
                        dayGroups.forEach((day) => {
                            (day.jobs || []).forEach((j) => jobMap.set(j.id, j));
                        });
                        this.allJobs = Array.from(jobMap.values());
                    }
                }
            } catch (err) {
                console.error("Map: failed to load jobs", err);
                this.allJobs = [];
            }

            this.applyFilters();
            this.loading = false;
        },

        // ── Company address loading ─────────────────────────────

        /**
         * Fetch the current user's company address and geocode it.
         * Cached in `companyAddress` so it's only fetched once.
         *
         * @returns {Promise<void>}
         */
        async loadCompanyAddress() {
            try {
                const resp = await authFetch("/api/company");
                if (!resp.ok) return;
                const company = await resp.json();
                const addr = company.address || "";
                const eircode = company.eircode || "";
                if (!addr && !eircode) return;

                // Geocode the company address to get coordinates
                const query = eircode ? eircode + ", Ireland" : addr;
                const result = await geocodeAddress(query);
                if (result) {
                    this.companyAddress = {
                        lat: result.lat,
                        lng: result.lng,
                        address: addr || result.formatted_address,
                    };
                }
            } catch (err) {
                console.debug("Map: failed to load company address", err);
            }
        },

        // ── Filtering ────────────────────────────────────────────

        /**
         * Apply client-side status filter and re-render markers.
         *
         * For regular statuses: filters `allJobs` (from calendar API).
         * For "unscheduled": fetches fresh data from the queue API
         * and renders only those jobs.
         *
         * @returns {void}
         */
        applyFilters() {
            // "Unscheduled" is a special case — fetch from queue API
            if (this.filterStatus === "unscheduled") {
                this._fetchAndShowUnscheduled();
                return;
            }

            // Switching away from unscheduled — clear that data
            this.unscheduledJobs = [];

            let jobs = this.allJobs.filter(
                (j) => j.latitude != null && j.longitude != null
            );

            // Client-side status filter
            if (this.filterStatus) {
                jobs = jobs.filter((j) => j.status === this.filterStatus);
            }

            this.visibleJobs = jobs;
            this._renderMarkers();
        },

        /**
         * Fetch unscheduled jobs from the queue API and render them.
         *
         * Always fetches fresh data (no stale cache).  Guards against
         * race conditions: if the user changes the filter while the
         * request is in-flight, the result is discarded.
         *
         * @returns {Promise<void>}
         */
        async _fetchAndShowUnscheduled() {
            this.loading = true;
            try {
                const resp = await authFetch("/api/jobs/queue");
                if (resp.ok) {
                    const data = await resp.json();
                    this.unscheduledJobs = data.items || [];
                } else {
                    console.error("Map: queue API returned", resp.status);
                    this.unscheduledJobs = [];
                }
            } catch (err) {
                console.error("Map: failed to load unscheduled jobs", err);
                this.unscheduledJobs = [];
            }

            // Guard: user may have changed filter while request was in-flight
            if (this.filterStatus !== "unscheduled") {
                this.loading = false;
                return;
            }

            this.visibleJobs = this.unscheduledJobs.filter(
                (j) => j.latitude != null && j.longitude != null
            );
            this._renderMarkers();
            this.loading = false;
        },

        /**
         * Called when the employee dropdown changes.
         *
         * Triggers a full server-side re-fetch because employee
         * filtering uses the job_employees junction table which
         * can only be queried on the backend.
         *
         * @returns {void}
         */
        onEmployeeChange() {
            this.loadJobs();
        },

        // ── Marker rendering ─────────────────────────────────────

        /**
         * Check whether the map supports AdvancedMarkerElement (vector rendering).
         *
         * @returns {boolean} True if the map is a vector map.
         */
        // _isVectorMap and _pinIcon are now shared — see maps-utils.js:
        // _isVectorMap(map), _pinIconDataUrl(colour)

        /**
         * Clear existing markers and render new ones for visibleJobs.
         * Automatically detects whether the map is a vector map and
         * falls back to legacy google.maps.Marker when it is not.
         *
         * Also populates `markerByJobId` so tiles can cross-highlight
         * markers on hover.
         *
         * @returns {void}
         */
        _renderMarkers() {
            // 1. Tear down old clusterer using RAW ref (bypasses Alpine Proxy)
            if (_rawClusterer) {
                _rawClusterer.clearMarkers();
                _rawClusterer.setMap(null);
                _rawClusterer = null;
            }
            this.clusterer = null;

            // 2. Force-remove every tracked marker using RAW refs
            _rawMarkers.forEach((m) => {
                try { m.map = null; } catch (_) {}
                if (typeof m.setMap === "function") {
                    try { m.setMap(null); } catch (_) {}
                }
            });
            _rawMarkers = [];
            _rawMarkerByJobId = {};
            this.markers = [];
            this.markerByJobId = {};

            if (!_rawMap) return;

            const points = [];

            this.visibleJobs.forEach((job) => {
                // Pass raw map to avoid Alpine Proxy breaking Google Maps internals
                const created = createJobMarker(job, _rawMap);
                if (!created) return;

                const marker = created.marker;
                const isAdvanced = created.isAdvanced;

                // Attach page-specific event listeners
                if (isAdvanced) {
                    marker.addEventListener("gmp-click", () => {
                        if (this.routeMode) { this._toggleRouteStop(job); return; }
                        this._showInfoWindow(marker, job);
                    });
                    if (marker.content) {
                        marker.content.addEventListener("mouseenter", () => {
                            this.hoveredJobId = job.id;
                        });
                        marker.content.addEventListener("mouseleave", () => {
                            if (this.hoveredJobId === job.id) this.hoveredJobId = null;
                        });
                    }
                } else {
                    marker.addListener("click", () => {
                        if (this.routeMode) { this._toggleRouteStop(job); return; }
                        this._showInfoWindow(marker, job);
                    });
                    marker.addListener("mouseover", () => {
                        this.hoveredJobId = job.id;
                    });
                    marker.addListener("mouseout", () => {
                        if (this.hoveredJobId === job.id) this.hoveredJobId = null;
                    });
                }

                // Store for cross-highlight lookup (raw + Alpine-proxied)
                _rawMarkerByJobId[job.id] = marker;
                _rawMarkers.push(marker);
                this.markerByJobId[job.id] = marker;
                this.markers.push(marker);
                points.push({ lat: parseFloat(job.latitude), lng: parseFloat(job.longitude) });
            });

            // Set up clustering — use raw map to avoid proxy issues
            if (typeof markerClusterer !== "undefined" && markerClusterer.MarkerClusterer) {
                const useAdvanced = _isVectorMap(_rawMap);
                const clusterOpts = { map: _rawMap, markers: _rawMarkers };

                if (useAdvanced) {
                    clusterOpts.renderer = {
                        render({ count, position }) {
                            const size = count < 10 ? 34 : count < 50 ? 40 : 48;
                            const el = document.createElement("div");
                            el.textContent = String(count);
                            el.style.cssText =
                                `display:flex;align-items:center;justify-content:center;` +
                                `width:${size}px;height:${size}px;border-radius:50%;` +
                                `background:#0d9488;color:#fff;font-weight:700;font-size:13px;` +
                                `box-shadow:0 2px 6px rgba(0,0,0,.3);border:2px solid #fff;cursor:pointer;`;
                            return new google.maps.marker.AdvancedMarkerElement({
                                position,
                                content: el,
                                map: _rawMap,
                            });
                        },
                    };
                }

                _rawClusterer = new markerClusterer.MarkerClusterer(clusterOpts);
                this.clusterer = _rawClusterer;
            }

            // Fit bounds using raw map
            fitMapBounds(_rawMap, points);
        },

        /**
         * Show an info window for a job marker.
         *
         * @param {google.maps.marker.AdvancedMarkerElement} marker - The clicked marker.
         * @param {Object} job - The job data object.
         * @returns {void}
         */
        _showInfoWindow(marker, job) {
            const statusBadge = `<span style="display:inline-block;padding:1px 6px;border-radius:9999px;font-size:11px;font-weight:600;background:${STATUS_COLOURS[job.status] || "#6b7280"}20;color:${STATUS_COLOURS[job.status] || "#6b7280"}">${(job.status || "").replace("_", " ")}</span>`;

            const time = job.start_time
                ? new Date(job.start_time).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })
                : "Unscheduled";

            const customer = job.customer_name || "";
            const address = job.address || job.location || "";

            const directionsUrl = `https://www.google.com/maps/dir/?api=1&destination=${job.latitude},${job.longitude}`;

            const content = `
                <div style="max-width:260px;font-family:system-ui,sans-serif;">
                    <p style="margin:0 0 4px;font-size:14px;font-weight:600;color:#1f2937;">${this._escapeHtml(job.title || "Untitled Job")}</p>
                    <p style="margin:0 0 6px;">${statusBadge}</p>
                    ${customer ? `<p style="margin:0 0 2px;font-size:12px;color:#6b7280;">Customer: ${this._escapeHtml(customer)}</p>` : ""}
                    <p style="margin:0 0 2px;font-size:12px;color:#6b7280;">${this._escapeHtml(time)}</p>
                    ${address ? `<p style="margin:0 0 6px;font-size:12px;color:#6b7280;">${this._escapeHtml(address)}</p>` : ""}
                    <div style="display:flex;gap:8px;margin-top:6px;">
                        <a href="${directionsUrl}" target="_blank" rel="noopener noreferrer"
                           style="font-size:12px;color:#0d9488;text-decoration:none;font-weight:500;">Get Directions ↗</a>
                        <a href="/calendar" style="font-size:12px;color:#2563eb;text-decoration:none;font-weight:500;">View in Calendar ↗</a>
                    </div>
                </div>
            `;

            this.infoWindow.setContent(content);
            this.infoWindow.open({ anchor: marker, map: _rawMap });
        },

        // ── Route planning ───────────────────────────────────────

        /**
         * Toggle route planning mode on/off.
         *
         * @returns {void}
         */
        toggleRouteMode() {
            this.routeMode = !this.routeMode;
            if (this.routeMode) {
                // Lazy-init Places Autocomplete on the address input
                this.$nextTick(() => this._initRouteAutocomplete());
            } else {
                this.clearRoute();
            }
        },

        /**
         * Initialise Google Places Autocomplete on the route address input.
         * Called lazily when route mode is first activated.
         *
         * @returns {void}
         */
        _initRouteAutocomplete() {
            if (_routeAutocomplete) return;
            const input = document.getElementById("route-address-input");
            if (!input || !window.mapsReady) return;

            _routeAutocomplete = new google.maps.places.Autocomplete(input, {
                fields: ["geometry", "formatted_address"],
            });

            _routeAutocomplete.addListener("place_changed", () => {
                const place = _routeAutocomplete.getPlace();
                if (!place.geometry) {
                    this.customAddressCoords = null;
                    return;
                }
                this.customAddressCoords = {
                    lat: place.geometry.location.lat(),
                    lng: place.geometry.location.lng(),
                    address: place.formatted_address || this.customAddressInput,
                };
            });
        },

        /**
         * Add or remove a job from the route stops list.
         *
         * @param {Object} job - The job to toggle.
         * @returns {void}
         */
        _toggleRouteStop(job) {
            const idx = this.routeStops.findIndex((s) => s.id === job.id);
            if (idx >= 0) {
                this.routeStops.splice(idx, 1);
            } else {
                this.routeStops.push({
                    id: job.id,
                    title: job.title,
                    address: job.address || job.location || "",
                    lat: parseFloat(job.latitude),
                    lng: parseFloat(job.longitude),
                });
            }
            this._renderRouteMarkers();
        },

        /**
         * Remove a stop by index.
         *
         * @param {number} idx - The index of the stop to remove.
         * @returns {void}
         */
        removeStop(idx) {
            this.routeStops.splice(idx, 1);
            this._renderRouteMarkers();
            // Re-calculate if we already have a route displayed
            if (this.routeInfo && this._totalRouteStops() >= 2) {
                this.calculateRoute();
            } else {
                this.routeInfo = null;
                this._clearRoutePolyline();
            }
        },

        /**
         * Calculate and display a route between the selected stops.
         *
         * @returns {void}
         */
        calculateRoute() {
            const fullRoute = this._buildFullRoute();
            if (fullRoute.length < 2) return;

            this._clearRoutePolyline();

            calculateRoute(fullRoute, { map: _rawMap })
                .then((result) => {
                    this.routePolyline = result.polyline;
                    this.routeInfo = {
                        distance: result.summary.distance,
                        duration: result.summary.duration,
                    };
                    this._renderRouteMarkers();
                })
                .catch((err) => {
                    console.error("Directions request failed:", err.message);
                });
        },

        /**
         * Re-calculate the route with waypoint optimisation enabled.
         *
         * @returns {void}
         */
        optimizeRoute() {
            const fullRoute = this._buildFullRoute();
            if (fullRoute.length < 3) return;

            this._clearRoutePolyline();

            calculateRoute(fullRoute, { optimize: true, map: _rawMap })
                .then((result) => {
                    // Reorder job stops based on optimised waypoint order.
                    // Start/end locations stay fixed (they're origin/destination).
                    if (result.waypointOrder) {
                        const hasStart = !!this.startLocation;
                        const hasEnd = !!this.endLocation;
                        let waypointStops;

                        if (hasStart && hasEnd) {
                            waypointStops = [...this.routeStops];
                        } else if (hasStart) {
                            waypointStops = this.routeStops.slice(0, -1);
                        } else if (hasEnd) {
                            waypointStops = this.routeStops.slice(1);
                        } else {
                            waypointStops = this.routeStops.slice(1, -1);
                        }

                        const reordered = result.waypointOrder.map((i) => waypointStops[i]);

                        if (hasStart && hasEnd) {
                            this.routeStops = reordered;
                        } else if (hasStart) {
                            this.routeStops = [...reordered, this.routeStops[this.routeStops.length - 1]];
                        } else if (hasEnd) {
                            this.routeStops = [this.routeStops[0], ...reordered];
                        } else {
                            this.routeStops = [
                                this.routeStops[0],
                                ...reordered,
                                this.routeStops[this.routeStops.length - 1],
                            ];
                        }
                    }
                    this.routePolyline = result.polyline;
                    this.routeInfo = {
                        distance: result.summary.distance,
                        duration: result.summary.duration,
                    };
                    this._renderRouteMarkers();
                })
                .catch((err) => {
                    console.error("Optimised directions request failed:", err.message);
                });
        },

        /**
         * Extract total distance and duration from a directions result.
         *
         * @param {google.maps.DirectionsResult} result - The directions response.
         * @returns {void}
         */
        // _summariseRoute is now shared — see summariseRoute() in maps-utils.js

        /**
         * Clear the route and all stops.
         *
         * @returns {void}
         */
        clearRoute() {
            this.routeStops = [];
            this.routeInfo = null;
            this.startLocation = null;
            this.endLocation = null;
            this.customAddressInput = "";
            this.customAddressCoords = null;
            this._clearRoutePolyline();
            this._clearRouteMarkers();
        },

        /**
         * Render the route as a polyline on the map.
         *
         * @param {google.maps.DirectionsResult} result - The directions response.
         * @returns {void}
         */
        // _renderRoutePolyline is now shared — see renderRoutePolyline() in maps-utils.js

        /**
         * Remove the route polyline from the map.
         *
         * @returns {void}
         */
        _clearRoutePolyline() {
            clearRoutePolyline(this.routePolyline);
            this.routePolyline = null;
        },

        // ── Route helper methods ─────────────────────────────────

        /**
         * Build the full ordered route: [start?, ...jobStops, end?].
         *
         * @returns {Array<{ lat: number, lng: number }>}
         */
        _buildFullRoute() {
            const stops = [];
            if (this.startLocation) stops.push(this.startLocation);
            stops.push(...this.routeStops);
            if (this.endLocation) stops.push(this.endLocation);
            return stops;
        },

        /**
         * Total number of route points (start + job stops + end).
         *
         * @returns {number}
         */
        _totalRouteStops() {
            return (this.startLocation ? 1 : 0) + this.routeStops.length + (this.endLocation ? 1 : 0);
        },

        /**
         * Render numbered markers on the map for all route stops.
         * Called whenever stops are added, removed, or reordered.
         *
         * @returns {void}
         */
        _renderRouteMarkers() {
            this._clearRouteMarkers();
            if (!_rawMap || !this.routeMode) return;

            const fullRoute = this._buildFullRoute();
            if (fullRoute.length === 0) return;

            fullRoute.forEach((stop, idx) => {
                const pos = { lat: parseFloat(stop.lat), lng: parseFloat(stop.lng) };
                if (isNaN(pos.lat) || isNaN(pos.lng)) return;

                // Colour: green for first, red for last, teal for middle
                let colour = "#0d9488";
                if (idx === 0 && this.startLocation) colour = "#16a34a";
                else if (idx === fullRoute.length - 1 && this.endLocation) colour = "#dc2626";

                const result = createNumberedMarker(idx + 1, pos, _rawMap, { colour: colour });
                if (result) _rawRouteMarkers.push(result.marker);
            });
        },

        /**
         * Remove all numbered route markers from the map.
         *
         * @returns {void}
         */
        _clearRouteMarkers() {
            _rawRouteMarkers.forEach((m) => {
                try { m.map = null; } catch (_) {}
                if (typeof m.setMap === "function") {
                    try { m.setMap(null); } catch (_) {}
                }
            });
            _rawRouteMarkers = [];
        },

        // ── Custom / company stop methods ────────────────────────

        /**
         * Resolve the custom address input via geocoding (fallback if
         * autocomplete didn't fire). Returns the resolved coords or null.
         *
         * @returns {Promise<Object|null>} { lat, lng, address } or null.
         */
        async _resolveCustomAddress() {
            if (this.customAddressCoords) return this.customAddressCoords;
            const text = this.customAddressInput.trim();
            if (!text) return null;

            const result = await geocodeAddress(text);
            if (result) {
                this.customAddressCoords = {
                    lat: result.lat,
                    lng: result.lng,
                    address: result.formatted_address || text,
                };
                return this.customAddressCoords;
            }
            return null;
        },

        /**
         * Add the resolved custom address as a route stop.
         *
         * @returns {Promise<void>}
         */
        async addCustomStop() {
            const loc = await this._resolveCustomAddress();
            if (!loc) return;

            this.routeStops.push({
                id: "custom-" + Date.now(),
                title: loc.address,
                address: loc.address,
                lat: loc.lat,
                lng: loc.lng,
                isCustom: true,
            });
            this.customAddressInput = "";
            this.customAddressCoords = null;
            this._renderRouteMarkers();
        },

        /**
         * Set the resolved custom address as the start location.
         *
         * @returns {Promise<void>}
         */
        async setStartFromInput() {
            const loc = await this._resolveCustomAddress();
            if (!loc) return;
            this.startLocation = { lat: loc.lat, lng: loc.lng, address: loc.address };
            this.customAddressInput = "";
            this.customAddressCoords = null;
            this._renderRouteMarkers();
        },

        /**
         * Set the resolved custom address as the end location.
         *
         * @returns {Promise<void>}
         */
        async setEndFromInput() {
            const loc = await this._resolveCustomAddress();
            if (!loc) return;
            this.endLocation = { lat: loc.lat, lng: loc.lng, address: loc.address };
            this.customAddressInput = "";
            this.customAddressCoords = null;
            this._renderRouteMarkers();
        },

        /**
         * Add company address as a route stop.
         *
         * @returns {void}
         */
        addCompanyAsStop() {
            if (!this.companyAddress) return;
            this.routeStops.push({
                id: "company-" + Date.now(),
                title: "Company: " + this.companyAddress.address,
                address: this.companyAddress.address,
                lat: this.companyAddress.lat,
                lng: this.companyAddress.lng,
                isCustom: true,
            });
            this._renderRouteMarkers();
        },

        /** Set company address as route start. */
        setStartFromCompany() {
            if (!this.companyAddress) return;
            this.startLocation = { ...this.companyAddress };
            this._renderRouteMarkers();
        },

        /** Set company address as route end. */
        setEndFromCompany() {
            if (!this.companyAddress) return;
            this.endLocation = { ...this.companyAddress };
            this._renderRouteMarkers();
        },

        /** Clear the start location. */
        clearStartLocation() {
            this.startLocation = null;
            this._renderRouteMarkers();
            if (this.routeInfo) {
                this.routeInfo = null;
                this._clearRoutePolyline();
            }
        },

        /** Clear the end location. */
        clearEndLocation() {
            this.endLocation = null;
            this._renderRouteMarkers();
            if (this.routeInfo) {
                this.routeInfo = null;
                this._clearRoutePolyline();
            }
        },

        // ── Tiles panel helpers ───────────────────────────────────

        /**
         * Return the tiles to show in the panel.
         *
         * Includes all visibleJobs (which have coords) PLUS any
         * unscheduled jobs WITHOUT coords (shown as "No location"
         * tiles only). Jobs already in routeStops are excluded.
         *
         * @returns {Array<Object>} Remaining job tiles.
         */
        availableTiles() {
            const stopIds = new Set(this.routeStops.map((s) => s.id));

            // Start with visible jobs (already have coords)
            let tiles = this.visibleJobs.filter((j) => !stopIds.has(j.id));

            // When showing unscheduled, add no-coord jobs to tiles only
            if (this.filterStatus === "unscheduled") {
                const tileIds = new Set(tiles.map((t) => t.id));
                const noCoord = this.unscheduledJobs.filter(
                    (j) => (j.latitude == null || j.longitude == null) && !tileIds.has(j.id) && !stopIds.has(j.id)
                );
                tiles = tiles.concat(noCoord);
            }

            return tiles;
        },

        /**
         * Add a job tile directly to the route stops list.
         * Only works when route mode is active.
         *
         * @param {Object} job - The job object to add as a stop.
         * @returns {void}
         */
        addTileToRoute(job) {
            if (!this.routeMode) return;
            // Guard against duplicate stops
            if (this.routeStops.some((s) => s.id === job.id)) return;

            this.routeStops.push({
                id: job.id,
                title: job.title,
                address: job.address || job.location || "",
                lat: parseFloat(job.latitude),
                lng: parseFloat(job.longitude),
            });
            this._renderRouteMarkers();
        },

        /**
         * Set hoveredJobId when a tile is moused-over.
         * Triggers cross-highlighting of the corresponding map marker.
         *
         * @param {number} jobId - ID of the hovered job.
         * @returns {void}
         */
        hoverTile(jobId) {
            this.hoveredJobId = jobId;
            this._bounceMarker(jobId);
        },

        /**
         * Clear hoveredJobId when the mouse leaves a tile.
         *
         * @param {number} jobId - ID of the un-hovered job.
         * @returns {void}
         */
        unhoverTile(jobId) {
            if (this.hoveredJobId === jobId) this.hoveredJobId = null;
            this._stopBounceMarker(jobId);
        },

        /**
         * Zoom the map to a specific job's marker and open its info window.
         * Triggered by double-clicking a tile in the jobs panel.
         *
         * @param {Object} job - The job object to zoom to.
         * @returns {void}
         */
        zoomToJob(job) {
            if (!_rawMap || !job.latitude || !job.longitude) return;

            const pos = { lat: parseFloat(job.latitude), lng: parseFloat(job.longitude) };

            // Smooth pan + zoom
            _rawMap.panTo(pos);
            _rawMap.setZoom(17);

            // Open the info window on the marker
            const marker = _rawMarkerByJobId[job.id];
            if (marker) {
                this._showInfoWindow(marker, job);
                // Brief bounce to draw attention
                this._bounceMarker(job.id);
                setTimeout(() => this._stopBounceMarker(job.id), 1500);
            }
        },

        /**
         * Pan to a job's marker and show its info window (no zoom change).
         * Triggered by single-clicking a tile.
         *
         * @param {Object} job - The job object to focus.
         * @returns {void}
         */
        focusTile(job) {
            if (!_rawMap || !job.latitude || !job.longitude) return;

            const pos = { lat: parseFloat(job.latitude), lng: parseFloat(job.longitude) };
            _rawMap.panTo(pos);

            const marker = _rawMarkerByJobId[job.id];
            if (marker) {
                this._showInfoWindow(marker, job);
            }
        },

        /**
         * Reset the map view to fit all visible markers.
         *
         * @returns {void}
         */
        resetView() {
            if (!_rawMap) return;
            this.infoWindow && this.infoWindow.close();
            const points = this.visibleJobs
                .filter((j) => j.latitude != null && j.longitude != null)
                .map((j) => ({ lat: parseFloat(j.latitude), lng: parseFloat(j.longitude) }));
            fitMapBounds(_rawMap, points);
        },

        /**
         * Start a bounce animation on the marker corresponding to a
         * job ID.  Works for both Advanced and legacy markers.
         *
         * @param {number} jobId - Job whose marker to bounce.
         * @returns {void}
         */
        _bounceMarker(jobId) {
            const marker = _rawMarkerByJobId[jobId];
            if (!marker) return;

            // Legacy Marker supports setAnimation
            if (typeof marker.setAnimation === "function") {
                marker.setAnimation(google.maps.Animation.BOUNCE);
            }
            // AdvancedMarkerElement: add a CSS bounce class
            if (marker.content && marker.content.classList) {
                marker.content.classList.add("marker-bounce");
            }
        },

        /**
         * Stop bounce animation on a marker.
         *
         * @param {number} jobId - Job whose marker to stop bouncing.
         * @returns {void}
         */
        _stopBounceMarker(jobId) {
            const marker = _rawMarkerByJobId[jobId];
            if (!marker) return;

            if (typeof marker.setAnimation === "function") {
                marker.setAnimation(null);
            }
            if (marker.content && marker.content.classList) {
                marker.content.classList.remove("marker-bounce");
            }
        },

        // ── Display helpers ──────────────────────────────────────

        /**
         * Return a human-readable status label.
         *
         * @param {string} status - Raw status string (e.g. "in_progress").
         * @returns {string} Formatted label (e.g. "In Progress").
         */
        statusLabel(status) {
            return STATUS_LABELS[status] || status || "Unknown";
        },

        /**
         * Return the hex colour for a given status.
         *
         * @param {string} status - Raw status string.
         * @returns {string} Hex colour code.
         */
        statusColour(status) {
            return STATUS_COLOURS[status] || "#6b7280";
        },

        /**
         * Format an ISO datetime string to a short time display.
         * Returns empty string if the input is falsy.
         *
         * @param {string|null} isoStr - ISO 8601 datetime string.
         * @returns {string} Formatted time (e.g. "9:30 AM") or "".
         */
        formatTime(isoStr) {
            if (!isoStr) return "";
            try {
                return new Date(isoStr).toLocaleTimeString(undefined, {
                    hour: "numeric",
                    minute: "2-digit",
                });
            } catch (_) {
                return "";
            }
        },

        // ── Helpers ──────────────────────────────────────────────

        /**
         * Escape HTML entities to prevent XSS in info window content.
         *
         * @param {string} str - Raw string.
         * @returns {string} Escaped string.
         */
        _escapeHtml(str) {
            const div = document.createElement("div");
            div.appendChild(document.createTextNode(str));
            return div.innerHTML;
        },

        // ── Schedule modal ───────────────────────────────────────

        /**
         * Open the schedule-commit modal, populating stops from
         * the current routeStops list. Pre-fills any existing times.
         *
         * @returns {void}
         */
        openScheduleModal() {
            // Filter out custom stops (company/free-type) — only schedule real jobs
            const jobStops = this.routeStops.filter((s) => !s.isCustom);
            if (jobStops.length === 0) return;

            // Build stop entries with editable start/end times
            const stops = jobStops.map((s) => {
                // Find the full job object for pre-existing times
                const full = this.allJobs.find((j) => j.id === s.id)
                    || this.unscheduledJobs.find((j) => j.id === s.id);
                return {
                    id: s.id,
                    title: s.title,
                    address: s.address || "",
                    startTime: full && full.start_time
                        ? full.start_time.substring(0, 16) : "",
                    endTime: full && full.end_time
                        ? full.end_time.substring(0, 16) : "",
                };
            });

            this.scheduleModal = {
                open: true,
                employeeId: this.filterEmployee || "",
                targetDate: this.startDate || "",
                stops: stops,
                submitting: false,
                error: "",
                successCount: 0,
                failCount: 0,
                done: false,
            };
        },

        /**
         * Auto-fill times for all stops from a target date.
         * Sets each stop to 30-min slots starting at 08:00.
         * Only fills stops that don't already have times.
         *
         * @returns {void}
         */
        autoFillTimes() {
            if (!this.scheduleModal.targetDate) return;
            const base = this.scheduleModal.targetDate;
            let hour = 8;
            let min = 0;
            this.scheduleModal.stops.forEach((stop) => {
                if (!stop.startTime) {
                    const hh = String(hour).padStart(2, "0");
                    const mm = String(min).padStart(2, "0");
                    stop.startTime = `${base}T${hh}:${mm}`;
                    // Default 1-hour end time
                    const eH = String(hour + 1).padStart(2, "0");
                    stop.endTime = `${base}T${eH}:${mm}`;
                    hour += 1;
                    if (hour >= 18) { hour = 8; min = 30; }
                }
            });
        },

        /**
         * Check if all schedule modal stops have valid times and an employee.
         *
         * @returns {boolean} True if all required fields are filled.
         */
        scheduleModalValid() {
            if (!this.scheduleModal.employeeId) return false;
            return this.scheduleModal.stops.every(
                (s) => s.startTime && s.endTime
            );
        },

        /**
         * Commit the scheduled route — sequentially assigns each job
         * to the selected employee at the specified times.
         *
         * Uses POST /api/jobs/{id}/assign with {assigned_to, start_time, end_time}.
         *
         * @returns {Promise<void>}
         */
        async commitSchedule() {
            if (!this.scheduleModalValid()) return;

            this.scheduleModal.submitting = true;
            this.scheduleModal.error = "";
            this.scheduleModal.successCount = 0;
            this.scheduleModal.failCount = 0;

            for (const stop of this.scheduleModal.stops) {
                try {
                    const resp = await authFetch(`/api/jobs/${stop.id}/assign`, {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({
                            assigned_to: parseInt(this.scheduleModal.employeeId, 10),
                            start_time: new Date(stop.startTime).toISOString(),
                            end_time: new Date(stop.endTime).toISOString(),
                        }),
                    });

                    if (resp.ok) {
                        this.scheduleModal.successCount++;
                    } else {
                        this.scheduleModal.failCount++;
                        const err = await resp.json().catch(() => null);
                        console.error(`Failed to schedule job ${stop.id}:`, err);
                    }
                } catch (err) {
                    this.scheduleModal.failCount++;
                    console.error(`Error scheduling job ${stop.id}:`, err);
                }
            }

            this.scheduleModal.submitting = false;
            this.scheduleModal.done = true;

            // If all succeeded, refresh data after a short delay
            if (this.scheduleModal.failCount === 0) {
                setTimeout(() => {
                    this.scheduleModal.open = false;
                    this.clearRoute();
                    this.filterStatus = "";
                    this.unscheduledJobs = [];
                    this.loadJobs();
                }, 1500);
            }
        },

        /**
         * Close the schedule modal and reset state.
         *
         * @returns {void}
         */
        closeScheduleModal() {
            this.scheduleModal.open = false;
        },
    };
}
