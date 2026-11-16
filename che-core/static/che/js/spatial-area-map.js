/* WMO-CHE spatial area editor. Uses CAP Composer's installed map libraries,
 * but does not call CAP-specific alert/severity/area-registry code.
 * Stores GeoJSON Polygon/MultiPolygon geometry in CHEEvent.spatial_area JSONField.
 */
(function () {
  "use strict";

  function isPolygon(geometry) {
    return geometry && (geometry.type === "Polygon" || geometry.type === "MultiPolygon") &&
      Array.isArray(geometry.coordinates) && geometry.coordinates.length > 0;
  }

  function readGeometry(raw) {
    if (!raw || !raw.trim() || raw.trim() === "null") return null;
    const parsed = JSON.parse(raw);
    const geometry = parsed.type === "Feature" ? parsed.geometry : parsed;
    if (!isPolygon(geometry)) throw new Error("Saved area must be a GeoJSON Polygon or MultiPolygon.");
    return geometry;
  }


  // CHE_DATE_COUNTRY_STEP151: navigation-only country and territory search.
  // No call to sync(); no modification of the GeoJSON form input.
  function installCountrySearch(wrapper, canvas, map) {
    if (wrapper.querySelector('[data-che-country-search]')) return;
    var panel = document.createElement('div');
    panel.className = 'che-country-search';
    panel.setAttribute('data-che-country-search', '');
    var search = document.createElement('input');
    search.type = 'search';
    search.placeholder = 'Country or territory (e.g. Cayman Islands)';
    search.setAttribute('aria-label', 'Search country or territory to zoom map');
    var button = document.createElement('button');
    button.type = 'button';
    button.textContent = 'Find on map';
    var results = document.createElement('select');
    results.setAttribute('aria-label', 'Choose a country or territory');
    results.hidden = true;
    var message = document.createElement('p');
    message.className = 'che-country-message';
    message.setAttribute('role', 'status');
    message.textContent = 'Country search only zooms the map; it does not set the event area. Uses OpenStreetMap Nominatim.';
    panel.appendChild(search);
    panel.appendChild(button);
    panel.appendChild(results);
    panel.appendChild(message);
    canvas.parentNode.insertBefore(panel, canvas);
    var lastSearch = 0;
    var candidates = [];
    function zoom(item) {
      if (!item || !Array.isArray(item.boundingbox) || item.boundingbox.length !== 4) return;
      // Nominatim ordering: [south latitude, north latitude, west longitude, east longitude].
      var b = item.boundingbox.map(Number);
      if (b.some(function (n) { return !Number.isFinite(n); })) return;
      map.fitBounds([[b[2], b[0]], [b[3], b[1]]], { padding: 32, maxZoom: 11, duration: 700 });
      message.textContent = 'Zoomed to ' + (item.display_name || 'selected location') + '. The event polygon is unchanged.';
    }
    button.addEventListener('click', function () {
      var q = search.value.trim();
      if (q.length < 2) { message.textContent = 'Enter a country or territory name.'; return; }
      if (Date.now() - lastSearch < 1100) {
        message.textContent = 'Please leave at least one second between searches.';
        return;
      }
      lastSearch = Date.now();
      button.disabled = true;
      results.hidden = true;
      message.textContent = 'Searching country/territory names…';
      var url = 'https://nominatim.openstreetmap.org/search?format=jsonv2&limit=5&addressdetails=1&q=' + encodeURIComponent(q);
      fetch(url, { headers: { 'Accept': 'application/json' } })
        .then(function (response) { if (!response.ok) throw Error('Search service HTTP ' + response.status); return response.json(); })
        .then(function (items) {
          // Country/territory boundary hits first; avoid navigating to an
          // unrelated village or street with a similar name.
          candidates = items.filter(function (it) {
            return Array.isArray(it.boundingbox) &&
              (it.addresstype === 'country' || it.addresstype === 'territory' ||
               (it.category === 'boundary' && it.type === 'administrative' && Number(it.place_rank) <= 10));
          });
          while (results.firstChild) results.removeChild(results.firstChild);
          var prompt = document.createElement('option');
          prompt.value = '';
          prompt.textContent = 'Select a country/territory…';
          results.appendChild(prompt);
          candidates.forEach(function (item, index) {
            var option = document.createElement('option');
            option.value = String(index);
            option.textContent = item.display_name;
            results.appendChild(option);
          });
          results.hidden = candidates.length === 0;
          message.textContent = candidates.length
            ? 'Choose the correct country/territory from the results.'
            : 'No matching country or territory found. Try the official name.';
        })
        .catch(function (error) {
          message.textContent = 'Country search is unavailable: ' + error.message + '. You can still pan/zoom and draw polygons manually.';
        })
        .finally(function () { button.disabled = false; });
    });
    search.addEventListener('keydown', function (event) {
      if (event.key === 'Enter') { event.preventDefault(); button.click(); }
    });
    results.addEventListener('change', function () {
      if (results.value !== '') zoom(candidates[Number(results.value)]);
    });
  }

  function initialise(wrapper) {
    if (wrapper.dataset.cheMapInitialised === "true") return;
    wrapper.dataset.cheMapInitialised = "true";

    const canvas = wrapper.querySelector("[data-che-map-canvas]");
    const input = wrapper.querySelector("[data-che-map-value]");
    const message = wrapper.querySelector("[data-che-map-message]");
    const clear = wrapper.querySelector("[data-che-map-clear]");
    if (!canvas || !input) return;
    if (typeof maplibregl === "undefined" || typeof MapboxDraw === "undefined") {
      message.textContent = "Map libraries could not load. Please reload the page.";
      return;
    }

    let existing = null;
    try { existing = readGeometry(input.value); }
    catch (error) { message.textContent = "Existing spatial area could not be displayed: " + error.message; }

    const map = new maplibregl.Map({
      container: canvas,
      style: "https://tiles.openfreemap.org/styles/liberty",
      center: [0, 10], zoom: 2
    });
    map.addControl(new maplibregl.NavigationControl(), "bottom-right");
    installCountrySearch(wrapper, canvas, map);
    const draw = new MapboxDraw({ displayControlsDefault: false, controls: { polygon: true, trash: true } });
    map.addControl(draw, "top-left");

    function sync() {
      const geometries = draw.getAll().features.map(function (feature) { return feature.geometry; });
      if (!geometries.length) {
        input.value = "";
        message.textContent = "No event area selected.";
        return;
      }
      // One CHE event can cover multiple separate polygons. GeoJSON MultiPolygon
      // represents multiple shapes without conflating them with multiple events.
      const polygons = [];
      geometries.forEach(function (geometry) {
        if (geometry.type === "Polygon") polygons.push(geometry.coordinates);
        else if (geometry.type === "MultiPolygon") polygons.push.apply(polygons, geometry.coordinates);
      });
      const geometry = polygons.length === 1
        ? { type: "Polygon", coordinates: polygons[0] }
        : { type: "MultiPolygon", coordinates: polygons };
      input.value = JSON.stringify(geometry);
      message.textContent = polygons.length + " polygon(s) ready to save with the CHE event.";
    }

    map.on("load", function () {
      if (existing) {
        draw.add({ type: "Feature", properties: {}, geometry: existing });
        const coords = [];
        function collect(node) {
          if (typeof node[0] === "number") coords.push(node);
          else node.forEach(collect);
        }
        collect(existing.coordinates);
        if (coords.length) {
          const bounds = new maplibregl.LngLatBounds();
          coords.forEach(function (point) { bounds.extend(point); });
          map.fitBounds(bounds, { padding: 40, maxZoom: 12 });
        }
        message.textContent = "Saved area loaded. Select the polygon to edit it.";
      } else if (!message.textContent) {
        message.textContent = "No event area selected.";
      }
      map.resize();
    });
    map.on("draw.create", sync);
    map.on("draw.update", sync);
    map.on("draw.delete", sync);
    clear.addEventListener("click", function () { draw.deleteAll(); sync(); });
  }

  function initialiseAll() {
    document.querySelectorAll("[data-che-map-widget]").forEach(initialise);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", initialiseAll);
  else initialiseAll();
})();
