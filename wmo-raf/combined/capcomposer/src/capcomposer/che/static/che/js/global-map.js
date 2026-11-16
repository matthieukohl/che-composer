/* Read-only CHE catalogue map. CAP alert code remains untouched. */
(() => {
    "use strict";
    const element = document.getElementById("che-global-map");
    const status = document.getElementById("che-map-status");
    if (!element || typeof maplibregl === "undefined") {
        if (status) status.textContent = "Unable to load map library.";
        return;
    }

    const map = new maplibregl.Map({
        container: element,
        style: "https://tiles.openfreemap.org/styles/liberty",
        center: [0, 15], zoom: 1.4
    });
    map.addControl(new maplibregl.NavigationControl(), "top-right");

    function popupFor(props) {
        const wrapper = document.createElement("div");
        wrapper.className = "che-map-popup";
        const heading = document.createElement("strong");
        heading.textContent = [props.event_type, props.hazard_specification].filter(Boolean).join(" — ");
        wrapper.appendChild(heading);
        for (const [label, value] of [["Status", props.status], ["Originator", props.originator], ["Start", props.event_start], ["Linked parent UUID", props.event_linkage]]) {
            if (!value) continue;
            const p = document.createElement("p");
            p.textContent = `${label}: ${value}`;
            wrapper.appendChild(p);
        }
        if (props.is_synthetic) {
            const caution = document.createElement("p");
            caution.textContent = "SYNTHETIC TEST EVENT — NOT REAL";
            wrapper.appendChild(caution);
        }
        const uuid = document.createElement("p");
        uuid.textContent = `UUID: ${props.event_id}`;
        wrapper.appendChild(uuid);
        return wrapper;
    }

    const fieldNames = ["q", "originator", "year", "event_type", "status"];
    const control = name => document.getElementById("che-filter-" + name);
    let requestSequence = 0;
    function setOptions(filters) {
        for (const [key, choices] of Object.entries({
            originator: (filters.originators || []).map(v => ({value:v,label:v})),
            year: (filters.years || []).map(v => ({value:String(v),label:String(v)})),
            event_type: filters.event_types || [],
            status: filters.statuses || [],
        })) {
            const el = control(key), previous = el.value;
            el.replaceChildren(new Option(({originator:"All institutions",year:"All years",event_type:"All types",status:"All statuses"})[key], ""));
            for (const c of choices) el.add(new Option(c.label, c.value));
            el.value = previous;
        }
    }

    // CHE-only event markers. Original affected-area geometry is untouched.
    let hazardMarkers = [];

    function representativeLocation(geometry) {
        if (!geometry || !geometry.coordinates) return null;

        const positions = [];

        function collect(coordinates) {
            if (!Array.isArray(coordinates)) return;
            if (typeof coordinates[0] === "number" &&
                typeof coordinates[1] === "number") {
                const lon = coordinates[0];
                const lat = coordinates[1];
                if (Number.isFinite(lon) && Number.isFinite(lat)) {
                    positions.push([lon, lat]);
                }
                return;
            }
            coordinates.forEach(collect);
        }

        collect(geometry.coordinates);
        if (!positions.length) return null;

        const lons = positions.map(point => point[0]);
        const lats = positions.map(point => point[1]);

        return [
            (Math.min(...lons) + Math.max(...lons)) / 2,
            (Math.min(...lats) + Math.max(...lats)) / 2
        ];
    }

    function renderHazardSymbols(features) {
        hazardMarkers.forEach(marker => marker.remove());
        hazardMarkers = [];

        const show = document.getElementById("che-show-symbols");
        if (!show || !show.checked) return;

        for (const feature of features) {
            const coordinates = representativeLocation(feature.geometry);
            if (!coordinates) continue;

            const properties = feature.properties || {};
            const symbol =
                (window.CHE_HAZARD_SYMBOLS || {})[properties.event_type_value]
                || "⚠️";

            const element = document.createElement("button");
            element.type = "button";
            element.textContent = symbol;
            element.title = properties.event_type || "CHE hazardous event";
            element.setAttribute(
                "aria-label",
                "View " + (properties.event_type || "CHE event")
            );

            Object.assign(element.style, {
                border: "1px solid #64748b",
                borderRadius: "50%",
                background: "rgba(255,255,255,0.94)",
                width: "32px",
                height: "32px",
                fontSize: "19px",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                cursor: "pointer",
                boxShadow: "0 1px 4px rgba(0,0,0,0.2)"
            });

            element.addEventListener("click", event => {
                event.stopPropagation();
                new maplibregl.Popup()
                    .setLngLat(coordinates)
                    .setDOMContent(popupFor(properties))
                    .addTo(map);
            });

            const marker = new maplibregl.Marker({
                element: element,
                anchor: "center"
            }).setLngLat(coordinates).addTo(map);

            hazardMarkers.push(marker);
        }
    }


    // Display explicitly recorded CHE parent-child links only.
    // Original event footprints and coordinates are never modified.
    function renderEventRelationships(features) {
        const enabled = document.getElementById("che-show-links").checked;
        const eventsByUUID = new Map();

        for (const feature of features) {
            const properties = feature.properties || {};
            if (properties.event_id) {
                eventsByUUID.set(
                    String(properties.event_id).toLowerCase(),
                    feature
                );
            }
        }

        const links = [];

        if (enabled) {
            for (const child of features) {
                const properties = child.properties || {};
                const parentUUID = properties.event_linkage;
                if (!parentUUID) continue;

                const parent = eventsByUUID.get(
                    String(parentUUID).toLowerCase()
                );
                if (!parent || parent === child) continue;

                const start = representativeLocation(parent.geometry);
                const end = representativeLocation(child.geometry);
                if (!start || !end) continue;

                links.push({
                    type: "Feature",
                    geometry: {
                        type: "LineString",
                        coordinates: [start, end]
                    },
                    properties: {
                        parent_uuid: parent.properties.event_id,
                        child_uuid: properties.event_id,
                        child_type: properties.event_type
                    }
                });
            }
        }

        const data = {
            type: "FeatureCollection",
            features: links
        };

        const source = map.getSource("che-event-relationships");

        if (source) {
            source.setData(data);
        } else {
            map.addSource("che-event-relationships", {
                type: "geojson",
                data
            });

            map.addLayer({
                id: "che-event-relationships-line",
                type: "line",
                source: "che-event-relationships",
                paint: {
                    "line-color": "#7c3aed",
                    "line-width": 2.5,
                    "line-dasharray": [3, 2],
                    "line-opacity": 0.85
                }
            });

            map.on("click", "che-event-relationships-line", event => {
                const feature = event.features && event.features[0];
                if (!feature) return;

                const details = document.createElement("div");
                const heading = document.createElement("strong");
                heading.textContent = "Recorded CHE event relationship";
                details.appendChild(heading);

                for (const [label, value] of [
                    ["Parent UUID", feature.properties.parent_uuid],
                    ["Child UUID", feature.properties.child_uuid],
                    ["Child event type", feature.properties.child_type]
                ]) {
                    const line = document.createElement("p");
                    line.textContent = label + ": " + value;
                    details.appendChild(line);
                }

                new maplibregl.Popup()
                    .setLngLat(event.lngLat)
                    .setDOMContent(details)
                    .addTo(map);
            });

            map.on("mouseenter", "che-event-relationships-line", () => {
                map.getCanvas().style.cursor = "pointer";
            });

            map.on("mouseleave", "che-event-relationships-line", () => {
                map.getCanvas().style.cursor = "";
            });
        }
    }

    async function refresh() {
        const sequence = ++requestSequence;

        try {
            const query = new URLSearchParams();
            for (const name of fieldNames) if (control(name).value.trim()) query.set(name, control(name).value.trim());
            const response = await fetch(element.dataset.geojsonUrl + "?" + query, {credentials: "same-origin"});
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const data = await response.json();
            if (sequence !== requestSequence) return;
            renderHazardSymbols(data.features);
            renderEventRelationships(data.features);
            if (!map.getSource("che-polygons")) setOptions(data.filters || {});
            const polygonFeatures = data.features.filter(f => ["Polygon", "MultiPolygon"].includes(f.geometry.type));
            const otherFeatures = data.features.filter(f => !["Polygon", "MultiPolygon"].includes(f.geometry.type));
            const polygonData = {type: "FeatureCollection", features: polygonFeatures};
            if (map.getSource("che-polygons")) {
                map.getSource("che-polygons").setData(polygonData);
            } else {
                map.addSource("che-polygons", {type: "geojson", data: polygonData});
            map.addLayer({id: "che-polygons-fill", type: "fill", source: "che-polygons", paint: {"fill-color": ["case", ["get", "is_synthetic"], "#3278bb", "#db8733"], "fill-opacity": 0.35}});
            map.addLayer({id: "che-polygons-line", type: "line", source: "che-polygons", paint: {"line-color": "#234d79", "line-width": 1.6}});
            for (const id of ["che-polygons-fill", "che-polygons-line"]) {
                map.on("click", id, event => {
                    const feature = event.features && event.features[0];
                    if (feature) new maplibregl.Popup().setLngLat(event.lngLat).setDOMContent(popupFor(feature.properties)).addTo(map);
                });
                map.on("mouseenter", id, () => {map.getCanvas().style.cursor = "pointer";});
                map.on("mouseleave", id, () => {map.getCanvas().style.cursor = "";});
            }
            }
            status.textContent = `${data.features.length} matching events with geographical data.  ${otherFeatures.length ? otherFeatures.length + " non-polygon geometries are not yet displayed. " : ""}${data.invalid_count ? data.invalid_count + " invalid geometries skipped." : ""} Synthetic polygons are illustrative, not observed hazard footprints.`;
        } catch (error) {
            status.textContent = `Could not load event geometries: ${error.message}`;
        }
    }
    map.on("load", () => {
        document.getElementById("che-show-symbols")
            .addEventListener("change", refresh);
        document.getElementById("che-show-links")
            .addEventListener("change", refresh);
        refresh();
        for (const name of fieldNames) {
            control(name).addEventListener(name === "q" ? "input" : "change", () => {
                // A sequence check prevents stale search responses from replacing newer results.
                refresh();
            });
        }
        control("clear").addEventListener("click", () => {
            for (const name of fieldNames) control(name).value = "";
            refresh();
        });
    });
})();
