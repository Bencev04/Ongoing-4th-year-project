/**
 * Google Maps utility functions for the Workflow Platform.
 *
 * Loaded only on pages that need maps via the {% block head_maps %} block.
 * All functions check window.mapsReady and gracefully degrade (no-op +
 * console.debug) if the Google Maps JS API has not loaded.
 *
 * @file maps-utils.js
 */

/* global google */

// ──────────────────────────────────────────────────────────────────────────────
// API readiness
// ──────────────────────────────────────────────────────────────────────────────

/** @type {boolean} */
window.mapsReady = false;

/**
 * Global callback invoked by the Google Maps JS API `callback` parameter.
 * Sets the readiness flag and dispatches a custom DOM event so Alpine.js
 * components (or any listener) can react.
 *
 * @returns {void}
 */
function initMapsReady() {
    window.mapsReady = true;
    document.dispatchEvent(new CustomEvent("mapsReady"));
}

// ──────────────────────────────────────────────────────────────────────────────
// Address Autocomplete
// ──────────────────────────────────────────────────────────────────────────────

/**
 * Attach Google Places Autocomplete to a text input.
 *
 * On `place_changed` the function extracts lat/lng, formatted address, and
 * Eircode (postal_code) from `address_components`, then populates the
 * corresponding hidden fields and optionally renders a map preview.
 *
 * @param {string} inputId - DOM id of the address `<input>`.
 * @param {Object} [options={}] - Configuration options.
 * @param {string} [options.latField] - DOM id of the hidden latitude input.
 * @param {string} [options.lngField] - DOM id of the hidden longitude input.
 * @param {string} [options.eircodeField] - DOM id of the eircode input.
 * @param {string} [options.mapPreview] - DOM id of a container for a map preview.
 * @returns {google.maps.places.Autocomplete|null} The Autocomplete instance, or null.
 */
function initAddressAutocomplete(inputId, options) {
    if (!window.mapsReady) {
        console.debug("[maps-utils] API not ready — skipping autocomplete for", inputId);
        return null;
    }

    const input = document.getElementById(inputId);
    if (!input) {
        console.debug("[maps-utils] Input not found:", inputId);
        return null;
    }

    const opts = options || {};

    const autocomplete = new google.maps.places.Autocomplete(input, {
        componentRestrictions: { country: "ie" },
        fields: ["address_components", "formatted_address", "geometry"],
    });

    autocomplete.addListener("place_changed", function () {
        const place = autocomplete.getPlace();
        if (!place.geometry) return;

        const lat = place.geometry.location.lat();
        const lng = place.geometry.location.lng();

        // Populate hidden lat/lng fields
        if (opts.latField) {
            const el = document.getElementById(opts.latField);
            if (el) el.value = lat;
        }
        if (opts.lngField) {
            const el = document.getElementById(opts.lngField);
            if (el) el.value = lng;
        }

        // Extract Eircode from address_components
        if (opts.eircodeField && place.address_components) {
            const postal = place.address_components.find(function (c) {
                return c.types.includes("postal_code");
            });
            if (postal) {
                const el = document.getElementById(opts.eircodeField);
                if (el) el.value = postal.long_name;
            }
        }

        // Update the address input with formatted address
        input.value = place.formatted_address || input.value;

        // Show map preview if container specified
        if (opts.mapPreview) {
            renderStaticMap(opts.mapPreview, lat, lng);
        }
    });

    return autocomplete;
}

// ──────────────────────────────────────────────────────────────────────────────
// Eircode Resolver
// ──────────────────────────────────────────────────────────────────────────────

/**
 * Resolve an Eircode to an address + lat/lng on blur or Enter key.
 *
 * Uses the Google Maps Geocoder to look up the Eircode value and populate
 * the associated address and coordinate fields.
 *
 * @param {string} eircodeInputId - DOM id of the Eircode input.
 * @param {string} addressInputId - DOM id of the address input to populate.
 * @param {string} latId - DOM id of the hidden latitude input.
 * @param {string} lngId - DOM id of the hidden longitude input.
 * @returns {void}
 */
function initEircodeResolver(eircodeInputId, addressInputId, latId, lngId) {
    if (!window.mapsReady) {
        console.debug("[maps-utils] API not ready — skipping eircode resolver");
        return;
    }

    const eircodeInput = document.getElementById(eircodeInputId);
    if (!eircodeInput) return;

    /** @param {Event} _event */
    function resolve(_event) {
        const eircode = eircodeInput.value.trim();
        if (!eircode) return;

        geocodeAddress(eircode + ", Ireland").then(function (result) {
            if (!result) return;

            const addrEl = document.getElementById(addressInputId);
            if (addrEl) addrEl.value = result.formatted_address;

            const latEl = document.getElementById(latId);
            if (latEl) latEl.value = result.lat;

            const lngEl = document.getElementById(lngId);
            if (lngEl) lngEl.value = result.lng;
        });
    }

    eircodeInput.addEventListener("blur", resolve);
    eircodeInput.addEventListener("keydown", function (e) {
        if (e.key === "Enter") {
            e.preventDefault();
            resolve(e);
        }
    });
}

// ──────────────────────────────────────────────────────────────────────────────
// Eircode Auto-Populate (Server-Side)
// ──────────────────────────────────────────────────────────────────────────────

/**
 * Debounced server-side eircode resolver.
 *
 * Listens on the eircode input for typing events. After a 400 ms debounce,
 * calls the maps-access-service `/api/maps/geocode-eircode` endpoint
 * through the frontend proxy to resolve the eircode to an address, lat/lng.
 * Populates the associated fields and optionally renders a map preview.
 *
 * Dispatches native `input` events on populated fields so Alpine.js
 * `x-model` bindings pick up the programmatic changes.
 *
 * @param {string} eircodeInputId - DOM id of the eircode input.
 * @param {string} addressInputId - DOM id of the address input to populate.
 * @param {string} latId - DOM id of the hidden latitude input.
 * @param {string} lngId - DOM id of the hidden longitude input.
 * @param {Object} [options={}] - Extra configuration.
 * @param {string} [options.mapPreview] - DOM id of a container for a map preview.
 * @returns {void}
 */
function initEircodeAutoPopulate(eircodeInputId, addressInputId, latId, lngId, options) {
    var opts = options || {};
    var eircodeInput = document.getElementById(eircodeInputId);
    if (!eircodeInput) return;

    var debounceTimer = null;
    var spinner = null;

    // Create a tiny inline spinner next to the eircode input
    spinner = document.createElement("span");
    spinner.className = "eircode-spinner";
    spinner.style.cssText =
        "display:none;margin-left:8px;width:16px;height:16px;" +
        "border:2px solid #d1d5db;border-top-color:#0d9488;" +
        "border-radius:50%;animation:spin .6s linear infinite;" +
        "vertical-align:middle;";
    eircodeInput.parentNode.insertBefore(spinner, eircodeInput.nextSibling);

    // Ensure the @keyframes rule exists once
    if (!document.getElementById("eircode-spinner-style")) {
        var style = document.createElement("style");
        style.id = "eircode-spinner-style";
        style.textContent = "@keyframes spin{to{transform:rotate(360deg)}}";
        document.head.appendChild(style);
    }

    /**
     * Set a DOM element value and fire an `input` event for Alpine.js.
     * @param {HTMLInputElement|null} el
     * @param {string} value
     */
    function setVal(el, value) {
        if (!el) return;
        el.value = value;
        el.dispatchEvent(new Event("input", { bubbles: true }));
    }

    /**
     * Call the server-side geocode-eircode endpoint via the frontend proxy.
     * @param {string} eircode
     */
    function resolveEircode(eircode) {
        spinner.style.display = "inline-block";

        // Use authFetch (defined in base.html) to include JWT cookie
        authFetch("/api/maps/geocode-eircode", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ eircode: eircode }),
        })
            .then(function (resp) {
                if (!resp.ok) return null;
                return resp.json();
            })
            .then(function (data) {
                spinner.style.display = "none";
                if (!data || !data.success || !data.result) return;

                var r = data.result;

                setVal(document.getElementById(addressInputId), r.formatted_address || "");
                setVal(document.getElementById(latId), r.latitude != null ? String(r.latitude) : "");
                setVal(document.getElementById(lngId), r.longitude != null ? String(r.longitude) : "");

                // Render map preview if container specified and Maps API ready
                if (opts.mapPreview && r.latitude && r.longitude && window.mapsReady) {
                    renderStaticMap(opts.mapPreview, r.latitude, r.longitude);
                }
            })
            .catch(function () {
                // Fail silently — spinner disappears, no error shown to user
                spinner.style.display = "none";
            });
    }

    // Debounced input listener (400 ms)
    eircodeInput.addEventListener("input", function () {
        clearTimeout(debounceTimer);
        var eircode = eircodeInput.value.trim();
        // Irish eircodes are 7 chars (e.g. "D02XY45" or "D02 XY45")
        if (eircode.length < 3) return;

        debounceTimer = setTimeout(function () {
            resolveEircode(eircode);
        }, 400);
    });

    // Also resolve on Enter key (immediate, no debounce)
    eircodeInput.addEventListener("keydown", function (e) {
        if (e.key === "Enter") {
            e.preventDefault();
            clearTimeout(debounceTimer);
            var eircode = eircodeInput.value.trim();
            if (eircode.length >= 3) resolveEircode(eircode);
        }
    });
}

// ──────────────────────────────────────────────────────────────────────────────
// Static Map Rendering
// ──────────────────────────────────────────────────────────────────────────────

/**
 * Render a Google Map with a single marker inside a container element.
 *
 * @param {string} containerId - DOM id of the map container.
 * @param {number} lat - Latitude.
 * @param {number} lng - Longitude.
 * @param {Object} [options={}] - Optional map settings.
 * @param {number} [options.zoom=15] - Zoom level.
 * @returns {google.maps.Map|null} The Map instance, or null.
 */
function renderStaticMap(containerId, lat, lng, options) {
    if (!window.mapsReady) {
        console.debug("[maps-utils] API not ready — skipping map render");
        return null;
    }

    const container = document.getElementById(containerId);
    if (!container) return null;

    const opts = options || {};
    const position = { lat: Number(lat), lng: Number(lng) };

    container.style.display = "block";

    /** @type {google.maps.MapOptions} */
    const mapOpts = {
        center: position,
        zoom: opts.zoom || 15,
        disableDefaultUI: true,
        zoomControl: true,
    };
    // Inherit the configured Map ID if available
    const mapCanvas = document.getElementById("map-canvas");
    const mapId = (container.dataset && container.dataset.mapId) || (mapCanvas && mapCanvas.dataset.mapId) || "";
    if (mapId) mapOpts.mapId = mapId;

    const map = new google.maps.Map(container, mapOpts);

    new google.maps.marker.AdvancedMarkerElement({ position: position, map: map });

    return map;
}

// ──────────────────────────────────────────────────────────────────────────────
// Directions Rendering
// ──────────────────────────────────────────────────────────────────────────────

/**
 * Render driving directions between two points inside a container.
 *
 * @param {string} containerId - DOM id of the directions container.
 * @param {{ lat: number, lng: number }|string} origin - Start point.
 * @param {{ lat: number, lng: number }|string} destination - End point.
 * @returns {void}
 */
function renderDirections(containerId, origin, destination) {
    if (!window.mapsReady) {
        console.debug("[maps-utils] API not ready — skipping directions render");
        return;
    }

    const container = document.getElementById(containerId);
    if (!container) return;

    container.style.display = "block";

    /** @type {google.maps.MapOptions} */
    const dirMapOpts = {
        center: { lat: 53.35, lng: -6.26 },
        zoom: 8,
        disableDefaultUI: true,
        zoomControl: true,
    };
    const mapCanvas = document.getElementById("map-canvas");
    const dirMapId = (mapCanvas && mapCanvas.dataset.mapId) || "";
    if (dirMapId) dirMapOpts.mapId = dirMapId;

    const map = new google.maps.Map(container, dirMapOpts);

    const directionsService = new google.maps.DirectionsService();
    directionsService.route(
        {
            origin: origin,
            destination: destination,
            travelMode: google.maps.TravelMode.DRIVING,
        },
        function (result, status) {
            if (status === google.maps.DirectionsStatus.OK) {
                new google.maps.Polyline({
                    path: result.routes[0].overview_path,
                    strokeColor: "#0d9488",
                    strokeWeight: 4,
                    strokeOpacity: 0.8,
                    map: map,
                });
            } else {
                console.debug("[maps-utils] Directions request failed:", status);
            }
        }
    );
}

// ──────────────────────────────────────────────────────────────────────────────
// Client-side Geocoding
// ──────────────────────────────────────────────────────────────────────────────

/**
 * Promise-based client-side geocoding using google.maps.Geocoder.
 *
 * @param {string} address - The address or Eircode string to geocode.
 * @returns {Promise<{lat: number, lng: number, formatted_address: string}|null>}
 *     Resolved location or null if geocoding fails.
 */
function geocodeAddress(address) {
    if (!window.mapsReady) {
        console.debug("[maps-utils] API not ready — skipping geocode");
        return Promise.resolve(null);
    }

    const geocoder = new google.maps.Geocoder();

    return new Promise(function (resolve) {
        geocoder.geocode({ address: address }, function (results, status) {
            if (status === google.maps.GeocoderStatus.OK && results.length > 0) {
                resolve({
                    lat: results[0].geometry.location.lat(),
                    lng: results[0].geometry.location.lng(),
                    formatted_address: results[0].formatted_address,
                });
            } else {
                console.debug("[maps-utils] Geocode failed:", status);
                resolve(null);
            }
        });
    });
}

// ──────────────────────────────────────────────────────────────────────────────
// Shared Constants
// ──────────────────────────────────────────────────────────────────────────────

/**
 * Status → marker colour mapping.
 * Used by createJobMarker() and any component that needs to colour-code
 * jobs by their current status.
 *
 * @type {Record<string, string>}
 */
const STATUS_COLOURS = {
    scheduled: "#0d9488",   // teal-600
    in_progress: "#2563eb", // blue-600
    completed: "#16a34a",   // green-600
    pending: "#d97706",     // amber-600
    cancelled: "#dc2626",   // red-600
};

/**
 * Human-readable status labels (underscores → spaces, title-case).
 *
 * @type {Record<string, string>}
 */
const STATUS_LABELS = {
    scheduled: "Scheduled",
    in_progress: "In Progress",
    completed: "Completed",
    pending: "Pending",
    cancelled: "Cancelled",
};

// ──────────────────────────────────────────────────────────────────────────────
// Job Marker Factory
// ──────────────────────────────────────────────────────────────────────────────

/**
 * Create a Google Maps marker for a job.
 *
 * Supports both AdvancedMarkerElement (vector maps) and legacy Marker
 * (raster maps). The caller is responsible for attaching event listeners
 * since click/hover behaviour differs by context (map page vs. day modal).
 *
 * @param {Object} job - Job object with at least `latitude`, `longitude`,
 *     `title`, and `status`.
 * @param {google.maps.Map} map - The map instance to place the marker on.
 * @param {Object} [options={}] - Optional configuration.
 * @param {string} [options.colour] - Override the status-derived colour.
 * @param {number} [options.scale=1.1] - Pin scale (AdvancedMarkerElement only).
 * @returns {{ marker: google.maps.marker.AdvancedMarkerElement|google.maps.Marker, isAdvanced: boolean }|null}
 */
function createJobMarker(job, map, options) {
    if (!window.mapsReady || !map) return null;

    var lat = parseFloat(job.latitude);
    var lng = parseFloat(job.longitude);
    if (isNaN(lat) || isNaN(lng)) return null;

    var opts = options || {};
    var pos = { lat: lat, lng: lng };
    var colour = opts.colour || STATUS_COLOURS[job.status] || "#6b7280";
    var useAdvanced = _isVectorMap(map);
    var marker;

    if (useAdvanced) {
        var pin = new google.maps.marker.PinElement({
            background: colour,
            borderColor: colour,
            glyphColor: "#FFFFFF",
            scale: opts.scale || 1.1,
        });
        marker = new google.maps.marker.AdvancedMarkerElement({
            position: pos,
            map: map,
            title: job.title || "",
            content: pin.element || pin,
        });
    } else {
        marker = new google.maps.Marker({
            position: pos,
            map: map,
            title: job.title || "",
            icon: {
                url: _pinIconDataUrl(colour),
                scaledSize: new google.maps.Size(28, 40),
                anchor: new google.maps.Point(14, 40),
            },
        });
    }

    return { marker: marker, isAdvanced: useAdvanced };
}

/**
 * Detect whether a map is a vector map (supports AdvancedMarkerElement).
 *
 * Checks the Google Maps API for AdvancedMarkerElement availability and
 * whether the map has a mapId set.
 *
 * @param {google.maps.Map} map - The map to check.
 * @returns {boolean} True if AdvancedMarkerElement should be used.
 */
function _isVectorMap(map) {
    if (typeof google === "undefined") return false;
    if (!google.maps.marker || !google.maps.marker.AdvancedMarkerElement) return false;
    // AdvancedMarkerElement requires a Map ID; if none was set, fall back
    try {
        var mapId = map.getMapId && map.getMapId();
        return !!mapId;
    } catch (_) {
        return false;
    }
}

/**
 * Generate a data-URI SVG pin icon for legacy google.maps.Marker.
 *
 * @param {string} colour - Hex colour for the pin.
 * @returns {string} Data URI string.
 */
function _pinIconDataUrl(colour) {
    var svg =
        '<svg xmlns="http://www.w3.org/2000/svg" width="28" height="40" viewBox="0 0 28 40">' +
        '<path d="M14 0C6.27 0 0 6.27 0 14c0 10.5 14 26 14 26s14-15.5 14-26C28 6.27 21.73 0 14 0z" fill="' +
        colour +
        '"/>' +
        '<circle cx="14" cy="14" r="6" fill="#FFFFFF"/>' +
        "</svg>";
    return "data:image/svg+xml;charset=UTF-8," + encodeURIComponent(svg);
}

// ──────────────────────────────────────────────────────────────────────────────
// Map Bounds Utility
// ──────────────────────────────────────────────────────────────────────────────

/** Default centre when no points are available (Ireland). */
var _IRELAND_CENTRE = { lat: 53.35, lng: -6.26 };

/**
 * Fit a map's viewport to show all the given points.
 *
 * Handles edge cases: 0 points centres on Ireland at zoom 7, 1 point
 * centres on that point at zoom 14. For 2+ points, uses `fitBounds`.
 *
 * @param {google.maps.Map} map - The map instance to adjust.
 * @param {Array<{ lat: number, lng: number }>} points - Coordinate objects.
 * @param {Object} [options={}] - Optional settings.
 * @param {number} [options.maxZoom=15] - Maximum zoom level after fit.
 * @returns {void}
 */
function fitMapBounds(map, points, options) {
    if (!map) return;
    var opts = options || {};
    var maxZoom = opts.maxZoom != null ? opts.maxZoom : 15;

    if (!points || points.length === 0) {
        map.setCenter(_IRELAND_CENTRE);
        map.setZoom(7);
        return;
    }

    if (points.length === 1) {
        map.setCenter(points[0]);
        map.setZoom(14);
        return;
    }

    var bounds = new google.maps.LatLngBounds();
    points.forEach(function (p) { bounds.extend(p); });
    map.fitBounds(bounds);

    // Prevent zooming in too far (e.g. two points very close together)
    var listener = google.maps.event.addListener(map, "idle", function () {
        if (map.getZoom() > maxZoom) map.setZoom(maxZoom);
        google.maps.event.removeListener(listener);
    });
}

// ──────────────────────────────────────────────────────────────────────────────
// Route Calculation Utilities
// ──────────────────────────────────────────────────────────────────────────────

/**
 * Calculate a driving route between ordered stops using Google
 * Maps DirectionsService.
 *
 * @param {Array<{ lat: number, lng: number }>} stops - Ordered stops
 *     (first = origin, last = destination, middle = waypoints).
 *     Must have at least 2 entries.
 * @param {Object} [options={}] - Configuration.
 * @param {boolean} [options.optimize=false] - Optimise waypoint order.
 * @param {google.maps.Map|null} [options.map=null] - If provided, renders
 *     a polyline on this map and returns it in the result.
 * @param {string} [options.strokeColor="#0d9488"] - Polyline colour.
 * @param {number} [options.strokeWeight=4] - Polyline weight.
 * @param {number} [options.strokeOpacity=0.8] - Polyline opacity.
 * @returns {Promise<{ directionsResult: google.maps.DirectionsResult, summary: Object, polyline: google.maps.Polyline|null, waypointOrder: Array<number>|null }>}
 */
function calculateRoute(stops, options) {
    if (!window.mapsReady) {
        return Promise.reject(new Error("Google Maps API not ready"));
    }
    if (!stops || stops.length < 2) {
        return Promise.reject(new Error("At least 2 stops required"));
    }

    var opts = options || {};
    var origin = { lat: stops[0].lat, lng: stops[0].lng };
    var dest = { lat: stops[stops.length - 1].lat, lng: stops[stops.length - 1].lng };

    var waypoints = stops.slice(1, -1).map(function (s) {
        return { location: { lat: s.lat, lng: s.lng }, stopover: true };
    });

    var routeRequest = {
        origin: origin,
        destination: dest,
        waypoints: waypoints,
        travelMode: google.maps.TravelMode.DRIVING,
    };
    if (opts.optimize) {
        routeRequest.optimizeWaypoints = true;
    }

    /* Enable traffic-aware routing when requested.
     * Uses `departureTime` (defaults to "now") so the Directions API
     * returns `duration_in_traffic` on each leg.  This requires the
     * Google Maps Platform "Directions" API with a valid API key. */
    if (opts.traffic !== false) {
        routeRequest.drivingOptions = {
            departureTime: opts.departureTime || new Date(),
            trafficModel: google.maps.TrafficModel.BEST_GUESS,
        };
    }

    return new Promise(function (resolve, reject) {
        var svc = new google.maps.DirectionsService();
        svc.route(routeRequest, function (result, status) {
            if (status !== "OK") {
                reject(new Error("Directions request failed: " + status));
                return;
            }

            var summary = summariseRoute(result);
            var polyline = null;

            if (opts.map) {
                polyline = renderRoutePolyline(result, opts.map, {
                    strokeColor: opts.strokeColor,
                    strokeWeight: opts.strokeWeight,
                    strokeOpacity: opts.strokeOpacity,
                });
            }

            var waypointOrder = opts.optimize
                ? result.routes[0].waypoint_order
                : null;

            resolve({
                directionsResult: result,
                summary: summary,
                polyline: polyline,
                waypointOrder: waypointOrder,
            });
        });
    });
}

/**
 * Extract total distance and duration from a directions result.
 *
 * When the request included `drivingOptions.departureTime`, the API
 * returns `duration_in_traffic` on each leg.  This function reads
 * both the normal and traffic-adjusted durations, making them
 * available to the UI as separate fields.
 *
 * @param {google.maps.DirectionsResult} result - The directions response.
 * @returns {{ distance: string, duration: string, distanceMetres: number, durationSeconds: number, stopCount: number, durationInTraffic: string|null, durationInTrafficSeconds: number|null }}
 */
function summariseRoute(result) {
    var legs = result.routes[0].legs;
    var totalDist = 0;
    var totalSec = 0;
    var totalTrafficSec = 0;
    var hasTraffic = false;

    legs.forEach(function (leg) {
        totalDist += leg.distance.value;
        totalSec += leg.duration.value;

        /* duration_in_traffic is only present when the request
         * included a departure time (traffic-aware mode). */
        if (leg.duration_in_traffic) {
            totalTrafficSec += leg.duration_in_traffic.value;
            hasTraffic = true;
        }
    });

    var km = (totalDist / 1000).toFixed(1);
    var hrs = Math.floor(totalSec / 3600);
    var mins = Math.round((totalSec % 3600) / 60);

    /* Format traffic-adjusted duration if available */
    var trafficDuration = null;
    var trafficSec = null;
    if (hasTraffic) {
        trafficSec = totalTrafficSec;
        var tHrs = Math.floor(totalTrafficSec / 3600);
        var tMins = Math.round((totalTrafficSec % 3600) / 60);
        trafficDuration = tHrs > 0 ? tHrs + "h " + tMins + "m" : tMins + " min";
    }

    return {
        distance: km + " km",
        duration: hrs > 0 ? hrs + "h " + mins + "m" : mins + " min",
        distanceMetres: totalDist,
        durationSeconds: totalSec,
        stopCount: legs.length + 1,
        durationInTraffic: trafficDuration,
        durationInTrafficSeconds: trafficSec,
    };
}

/**
 * Render a route polyline on a map from a directions result.
 *
 * @param {google.maps.DirectionsResult} result - The directions response.
 * @param {google.maps.Map} map - The map to render on.
 * @param {Object} [options={}] - Polyline styling options.
 * @param {string} [options.strokeColor="#0d9488"] - Line colour.
 * @param {number} [options.strokeWeight=4] - Line weight.
 * @param {number} [options.strokeOpacity=0.8] - Line opacity.
 * @returns {google.maps.Polyline} The rendered polyline.
 */
function renderRoutePolyline(result, map, options) {
    var opts = options || {};
    var path = result.routes[0].overview_path;
    return new google.maps.Polyline({
        path: path,
        strokeColor: opts.strokeColor || "#0d9488",
        strokeWeight: opts.strokeWeight || 4,
        strokeOpacity: opts.strokeOpacity || 0.8,
        map: map,
    });
}

/**
 * Remove a route polyline from the map.
 *
 * @param {google.maps.Polyline|null} polyline - The polyline to remove.
 * @returns {void}
 */
function clearRoutePolyline(polyline) {
    if (polyline) {
        polyline.setMap(null);
    }
}

// ──────────────────────────────────────────────────────────────────────────────
// Numbered Route Marker Factory
// ──────────────────────────────────────────────────────────────────────────────

/**
 * Create a numbered marker for route stops.
 *
 * Renders a circular marker with a number inside. Supports both
 * AdvancedMarkerElement (vector maps) and legacy Marker (raster maps).
 * Used by the route planner to show stop order on the map.
 *
 * @param {number} number - The stop number to display (1-based).
 * @param {{ lat: number, lng: number }} position - Marker coordinates.
 * @param {google.maps.Map} map - The map instance.
 * @param {Object} [options={}] - Configuration.
 * @param {string} [options.colour="#0d9488"] - Background colour.
 * @returns {{ marker: google.maps.marker.AdvancedMarkerElement|google.maps.Marker, isAdvanced: boolean }|null}
 */
function createNumberedMarker(number, position, map, options) {
    if (!window.mapsReady || !map) return null;

    var opts = options || {};
    var colour = opts.colour || "#0d9488";
    var label = String(number);
    var useAdvanced = _isVectorMap(map);
    var marker;

    if (useAdvanced) {
        // Custom HTML element: circular badge with number
        var el = document.createElement("div");
        el.style.cssText =
            "display:flex;align-items:center;justify-content:center;" +
            "width:30px;height:30px;border-radius:50%;background:" + colour + ";" +
            "color:#fff;font-weight:700;font-size:14px;font-family:system-ui,sans-serif;" +
            "border:3px solid #fff;box-shadow:0 2px 8px rgba(0,0,0,0.35);cursor:pointer;";
        el.textContent = label;

        marker = new google.maps.marker.AdvancedMarkerElement({
            position: position,
            map: map,
            content: el,
            zIndex: 1000 + number,
        });
    } else {
        // Legacy marker with label overlay on a solid pin SVG
        marker = new google.maps.Marker({
            position: position,
            map: map,
            label: {
                text: label,
                color: "#FFFFFF",
                fontWeight: "bold",
                fontSize: "13px",
            },
            icon: {
                url: _numberedPinDataUrl(colour),
                scaledSize: new google.maps.Size(32, 44),
                anchor: new google.maps.Point(16, 44),
                labelOrigin: new google.maps.Point(16, 16),
            },
            zIndex: 1000 + number,
        });
    }

    return { marker: marker, isAdvanced: useAdvanced };
}

/**
 * Generate a data-URI SVG pin for numbered markers (legacy Marker).
 *
 * The pin is filled with colour and has a white stroke, but no inner
 * elements — Google Maps overlays the `label` text on top.
 *
 * @param {string} colour - Hex colour for the pin.
 * @returns {string} Data URI string.
 */
function _numberedPinDataUrl(colour) {
    var svg =
        '<svg xmlns="http://www.w3.org/2000/svg" width="32" height="44" viewBox="0 0 32 44">' +
        '<path d="M16 0C7.16 0 0 7.16 0 16c0 12 16 28 16 28s16-16 16-28C32 7.16 24.84 0 16 0z"' +
        ' fill="' + colour + '" stroke="#fff" stroke-width="2"/>' +
        "</svg>";
    return "data:image/svg+xml;charset=UTF-8," + encodeURIComponent(svg);
}
