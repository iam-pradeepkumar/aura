/* MapLibre full-screen SAR map with reliable polygon draw + live unit markers */

const AuraMap = (function () {
  let map = null;
  let mapReady = false;
  let drawPts = [];
  let closedZone = [];
  let drawMode = false;
  let survivorMode = false;
  let anchor = null;
  let onZoneChange = null;
  let onSurvivorChange = null;

  const unitMarkers = {};
  const survivorMarkers = {};
  const confirmedSurvivorStore = {};
  const placedSurvivorMarkers = {};
  let placedSurvivors = [];
  const vertexMarkers = [];
  const trails = {};
  let clickTimer = null;
  let zoneFitted = false;
  let missionActive = false;
  const placedSurvivorCoords = {};
  const missionSurvivorCoords = {};
  const STYLE = "https://tiles.openfreemap.org/styles/liberty";

  /** Keep HTML markers glued to map coordinates when the view is pitched. */
  function mapMarkerOpts(anchor = "bottom") {
    return { element: null, anchor, pitchAlignment: "map", rotationAlignment: "map" };
  }

  function makeMarker(el, coord, anchor = "bottom") {
    const opts = mapMarkerOpts(anchor);
    opts.element = el;
    return new maplibregl.Marker(opts).setLngLat(coord).addTo(map);
  }

  function init(containerId) {
    map = new maplibregl.Map({
      container: containerId,
      style: STYLE,
      center: [80.2707, 13.0827],
      zoom: 15,
      pitch: 60,
      bearing: -20,
      antialias: true,
    });

    map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), "bottom-right");
    map.addControl(new maplibregl.ScaleControl(), "bottom-left");

    map.on("load", () => {
      _addLayers();
      mapReady = true;
      map.resize();
      if (typeof AuraScene3D !== "undefined") AuraScene3D.attach(map);
    });

    map.on("click", (e) => {
      if (!mapReady) return;
      const pt = [e.lngLat.lng, e.lngLat.lat];
      if (survivorMode) {
        _addPlacedSurvivor(pt);
        return;
      }
      if (!drawMode) return;
      if (clickTimer) clearTimeout(clickTimer);
      clickTimer = setTimeout(() => {
        clickTimer = null;
        drawPts.push(pt);
        _addVertexMarker(pt);
        _updateDrawLayers();
        if (onZoneChange) onZoneChange(drawPts.slice());
      }, 220);
    });

    map.on("dblclick", (e) => {
      if (!drawMode) return;
      e.preventDefault();
      if (clickTimer) {
        clearTimeout(clickTimer);
        clickTimer = null;
      }
      closePolygon();
    });

    window.addEventListener("resize", () => map?.resize());
    return map;
  }

  function _addLayers() {
    if (map.getSource("zone-fill")) return;

    map.addSource("zone-fill", { type: "geojson", data: emptyFC() });
    map.addLayer({
      id: "zone-fill-layer",
      type: "fill",
      source: "zone-fill",
      paint: { "fill-color": "#f59e0b", "fill-opacity": 0.22 },
    });

    map.addSource("zone-line", { type: "geojson", data: emptyLine() });
    map.addLayer({
      id: "zone-line-layer",
      type: "line",
      source: "zone-line",
      paint: { "line-color": "#fbbf24", "line-width": 3 },
    });

    map.addSource("draw-line", { type: "geojson", data: emptyLine() });
    map.addLayer({
      id: "draw-line-layer",
      type: "line",
      source: "draw-line",
      paint: { "line-color": "#0ea5e9", "line-width": 2, "line-dasharray": [2, 1] },
    });

    map.addSource("trails", { type: "geojson", data: emptyFC() });
    map.addLayer({
      id: "trails-layer",
      type: "line",
      source: "trails",
      paint: { "line-color": ["get", "color"], "line-width": 2.5, "line-opacity": 0.75 },
    });

    map.addSource("survivor-pulse", { type: "geojson", data: emptyFC() });
    map.addLayer({
      id: "survivor-pulse-layer",
      type: "circle",
      source: "survivor-pulse",
      paint: {
        "circle-radius": 10,
        "circle-color": "#f59e0b",
        "circle-opacity": 0.18,
        "circle-blur": 0.5,
      },
    });

    map.addSource("units-dots", { type: "geojson", data: emptyFC() });
    map.addLayer({
      id: "units-dots-layer",
      type: "circle",
      source: "units-dots",
      paint: {
        "circle-radius": 6,
        "circle-color": ["get", "color"],
        "circle-opacity": 0.35,
        "circle-stroke-width": 1,
        "circle-stroke-color": "#ffffff",
        "circle-pitch-alignment": "map",
      },
    });

    map.addSource("wifi-beams", { type: "geojson", data: emptyFC() });
    map.addLayer({
      id: "wifi-beams-layer",
      type: "line",
      source: "wifi-beams",
      paint: {
        "line-color": "#0ea5e9",
        "line-width": ["*", ["get", "strength"], 5],
        "line-opacity": ["*", ["get", "strength"], 0.75],
        "line-blur": 0.5,
      },
    });

    map.addSource("wifi-zones", { type: "geojson", data: emptyFC() });
    map.addLayer({
      id: "wifi-zones-layer",
      type: "fill",
      source: "wifi-zones",
      paint: {
        "fill-color": "#0ea5e9",
        "fill-opacity": ["*", ["get", "strength"], 0.12],
      },
    });

    map.addSource("confirmed-survivors", { type: "geojson", data: emptyFC() });
    map.addLayer({
      id: "confirmed-survivors-layer",
      type: "circle",
      source: "confirmed-survivors",
      paint: {
        "circle-radius": 14,
        "circle-color": "#ef4444",
        "circle-stroke-width": 3,
        "circle-stroke-color": "#fecaca",
        "circle-opacity": 0.95,
      },
    });
  }

  function emptyFC() {
    return { type: "FeatureCollection", features: [] };
  }

  function emptyLine() {
    return { type: "Feature", geometry: { type: "LineString", coordinates: [] } };
  }

  function _addVertexMarker(coord) {
    const el = document.createElement("div");
    el.className = "draw-vertex";
    vertexMarkers.push(makeMarker(el, coord, "center"));
  }

  function _clearVertices() {
    vertexMarkers.forEach((m) => m.remove());
    vertexMarkers.length = 0;
  }

  function _updateDrawLayers() {
    if (!mapReady) return;
    const coords = drawPts.slice();
    map.getSource("draw-line").setData({
      type: "Feature",
      geometry: { type: "LineString", coordinates: coords },
    });
    if (coords.length >= 3) {
      map.getSource("zone-fill").setData({
        type: "FeatureCollection",
        features: [{
          type: "Feature",
          geometry: { type: "Polygon", coordinates: [[...coords, coords[0]]] },
        }],
      });
    }
  }

  function _setZone(ring, fit = false) {
    if (!mapReady || !ring || ring.length < 3) return;
    closedZone = ring.slice();
    const closed = [...ring, ring[0]];
    map.getSource("zone-line").setData({
      type: "Feature",
      geometry: { type: "LineString", coordinates: closed },
    });
    map.getSource("zone-fill").setData({
      type: "FeatureCollection",
      features: [{
        type: "Feature",
        geometry: { type: "Polygon", coordinates: [closed] },
      }],
    });
    if (fit && !missionActive) fitToZone(ring);
  }

  function fitToZone(ring) {
    if (!ring || ring.length < 3) return;
    const lngs = ring.map((p) => p[0]);
    const lats = ring.map((p) => p[1]);
    map.fitBounds(
      [[Math.min(...lngs), Math.min(...lats)], [Math.max(...lngs), Math.max(...lats)]],
      { padding: { top: 80, bottom: 140, left: 40, right: 320 }, pitch: 55, duration: 1200 }
    );
  }

  function flyTo(lat, lon, label) {
    anchor = { lat, lon, label };
    if (!mapReady) {
      map.once("load", () => flyTo(lat, lon, label));
      return;
    }
    map.flyTo({ center: [lon, lat], zoom: 17, pitch: 58, bearing: -15, duration: 1600 });
  }

  function getAnchor() {
    return anchor;
  }

  function _pointInClosedZone(lng, lat) {
    const ring = closedZone.length >= 3 ? closedZone : drawPts;
    if (ring.length < 3) return false;
    let inside = false;
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      const xi = ring[i][0], yi = ring[i][1];
      const xj = ring[j][0], yj = ring[j][1];
      if (((yi > lat) !== (yj > lat)) && (lng < (xj - xi) * (lat - yi) / (yj - yi + 1e-12) + xi)) {
        inside = !inside;
      }
    }
    return inside;
  }

  function _addPlacedSurvivor(coord) {
    if (!_pointInClosedZone(coord[0], coord[1])) return false;
    const id = placedSurvivors.length + 1;
    const entry = { id, lat: coord[1], lon: coord[0] };
    placedSurvivors.push(entry);
    placedSurvivorCoords[String(id)] = { lat: entry.lat, lon: entry.lon };
    const el = document.createElement("div");
    el.className = "placed-survivor-marker";
    el.innerHTML = `<span>${id}</span>`;
    el.title = `Placed survivor #${id}`;
    placedSurvivorMarkers[id] = makeMarker(el, coord, "center");
    if (onSurvivorChange) onSurvivorChange(placedSurvivors.slice());
    return true;
  }

  function setSurvivorMode(on) {
    survivorMode = on;
    if (on) setDrawMode(false);
    if (map) map.getCanvas().style.cursor = on ? "cell" : "";
  }

  function clearPlacedSurvivors() {
    Object.values(placedSurvivorMarkers).forEach((m) => m.remove());
    Object.keys(placedSurvivorMarkers).forEach((k) => delete placedSurvivorMarkers[k]);
    placedSurvivors = [];
    Object.keys(placedSurvivorCoords).forEach((k) => delete placedSurvivorCoords[k]);
    if (onSurvivorChange) onSurvivorChange([]);
  }

  function getPlacedSurvivors() {
    return placedSurvivors.slice();
  }

  function setDrawMode(on) {
    drawMode = on;
    if (on) setSurvivorMode(false);
    if (map) {
      map.getCanvas().style.cursor = on ? "crosshair" : "";
      if (on) {
        drawPts = [];
        closedZone = [];
        _clearVertices();
        if (mapReady) {
          map.getSource("draw-line")?.setData(emptyLine());
          map.getSource("zone-line")?.setData(emptyLine());
          map.getSource("zone-fill")?.setData(emptyFC());
        }
        map.doubleClickZoom.disable();
      } else {
        map.doubleClickZoom.enable();
      }
    }
  }

  function setMissionSurvivors(list) {
    Object.keys(missionSurvivorCoords).forEach((k) => delete missionSurvivorCoords[k]);
    (list || []).forEach((s) => {
      missionSurvivorCoords[String(s.id)] = { lat: s.lat, lon: s.lon };
    });
  }

  function clearMissionSurvivors() {
    Object.keys(missionSurvivorCoords).forEach((k) => delete missionSurvivorCoords[k]);
  }

  function clearMissionVisuals() {
    Object.values(unitMarkers).forEach((m) => m.remove());
    Object.values(survivorMarkers).forEach((m) => m.remove());
    Object.keys(unitMarkers).forEach((k) => delete unitMarkers[k]);
    Object.keys(survivorMarkers).forEach((k) => delete survivorMarkers[k]);
    Object.keys(confirmedSurvivorStore).forEach((k) => delete confirmedSurvivorStore[k]);
    Object.keys(trails).forEach((k) => delete trails[k]);
    missionActive = false;
    zoneFitted = false;
    if (mapReady) {
      map.getSource("trails")?.setData(emptyFC());
      map.getSource("units-dots")?.setData(emptyFC());
      map.getSource("wifi-beams")?.setData(emptyFC());
      map.getSource("wifi-zones")?.setData(emptyFC());
      map.getSource("survivor-pulse")?.setData(emptyFC());
      map.getSource("confirmed-survivors")?.setData(emptyFC());
    }
  }

  function clearDraw() {
    drawPts = [];
    closedZone = [];
    _clearVertices();
    clearMissionVisuals();
    clearPlacedSurvivors();
    if (mapReady) {
      map.getSource("draw-line")?.setData(emptyLine());
      map.getSource("zone-fill")?.setData(emptyFC());
      map.getSource("zone-line")?.setData(emptyLine());
    }
    if (onZoneChange) onZoneChange([]);
  }

  function setMissionActive(active) {
    missionActive = !!active;
    if (!active) zoneFitted = false;
  }

  function closePolygon() {
    if (drawPts.length < 3) return null;
    const ring = drawPts.slice();
    _setZone(ring, true);
    drawPts = [];
    _clearVertices();
    setDrawMode(false);
    if (mapReady) map.getSource("draw-line")?.setData(emptyLine());
    if (onZoneChange) onZoneChange(ring);
    return ring;
  }

  function getZoneGeo() {
    if (closedZone.length >= 3) return closedZone.slice();
    if (drawPts.length >= 3) return drawPts.slice();
    return null;
  }

  function _upsertUnitMarker(u) {
    if (u.lat == null || u.lon == null) return;
    const id = u.id;
    const coord = [u.lon, u.lat];

    if (!trails[id]) trails[id] = [];
    const last = trails[id][trails[id].length - 1];
    if (!last || Math.hypot(last[0] - coord[0], last[1] - coord[1]) > 0.0000015) {
      trails[id].push(coord);
      if (trails[id].length > 120) trails[id].shift();
    }

    const status = (u.status || "PATROL").toLowerCase();
    if (!unitMarkers[id]) {
      const el = document.createElement("div");
      el.className = `unit-marker ${u.type === "drone" ? "drone" : "spider"} ${status}`;
      el.innerHTML = `<div class="status-chip">${u.status || "PATROL"}</div><div class="unit-dot"></div>`;
      unitMarkers[id] = makeMarker(el, coord, "bottom");
    } else {
      unitMarkers[id].setLngLat(coord);
      const root = unitMarkers[id].getElement();
      root.className = `unit-marker ${u.type === "drone" ? "drone" : "spider"} ${status}`;
      const chip = root.querySelector(".status-chip");
      if (chip) chip.textContent = u.status || "PATROL";
    }
  }

  function _updateTrails(units) {
    if (!mapReady) return;
    const features = (units || []).map((u) => {
      const path = trails[u.id] || [];
      if (path.length < 2) return null;
      return {
        type: "Feature",
        geometry: { type: "LineString", coordinates: path },
        properties: { color: u.type === "drone" ? "#22c55e" : "#0ea5e9" },
      };
    }).filter(Boolean);
    map.getSource("trails").setData({ type: "FeatureCollection", features });
  }

  function updateUnits(units) {
    if (!mapReady) return;
    (units || []).forEach(_upsertUnitMarker);
    if (typeof AuraScene3D !== "undefined") AuraScene3D.updateUnitList(units);
    _updateTrails(units);
    map.getSource("units-dots").setData({
      type: "FeatureCollection",
      features: (units || []).filter((u) => u.lat != null && u.lon != null).map((u) => ({
        type: "Feature",
        geometry: { type: "Point", coordinates: [u.lon, u.lat] },
        properties: { color: u.type === "drone" ? "#22c55e" : "#0ea5e9" },
      })),
    });
  }

  function fitToUnits(units) {
    const pts = (units || []).filter((u) => u.lat != null && u.lon != null);
    if (!pts.length) return;
    const lngs = pts.map((u) => u.lon);
    const lats = pts.map((u) => u.lat);
    if (closedZone.length >= 3) {
      lngs.push(...closedZone.map((p) => p[0]));
      lats.push(...closedZone.map((p) => p[1]));
    }
    map.fitBounds(
      [[Math.min(...lngs), Math.min(...lats)], [Math.max(...lngs), Math.max(...lats)]],
      { padding: { top: 80, bottom: 140, left: 40, right: 320 }, pitch: 55, duration: 800, maxZoom: 18 }
    );
  }

  function _resolveSurvivorCoord(t) {
    const id = String(t.id);
    const placed = missionSurvivorCoords[id]
      || placedSurvivorCoords[id]
      || placedSurvivors.find((p) => String(p.id) === id);
    const prob = t.probability_pct ?? Math.round((t.confidence || 0) * 100);
    const isConfirmed = t.confirmed || prob >= 55 || t.suggested_triage === "START";
    if (placed) {
      return { lat: placed.lat, lon: placed.lon, confirmed: isConfirmed };
    }
    if (t.lat != null && t.lon != null) {
      return { lat: t.lat, lon: t.lon, confirmed: isConfirmed };
    }
    return null;
  }

  function updateSurvivors(targets) {
    if (!mapReady) return;
    (targets || []).forEach((t) => {
      const resolved = _resolveSurvivorCoord(t);
      if (!resolved) return;
      const id = String(t.id);
      const prob = t.probability_pct ?? Math.round((t.confidence || 0) * 100);
      const isConfirmed = resolved.confirmed;
      if (isConfirmed) {
        confirmedSurvivorStore[id] = { ...t, lat: resolved.lat, lon: resolved.lon, confirmed: true };
      }
    });

    const all = Object.values(confirmedSurvivorStore);
    (targets || []).forEach((t) => {
      const id = String(t.id);
      if (!confirmedSurvivorStore[id]) all.push(t);
    });

    const confirmedFeatures = [];
    all.forEach((t) => {
      const resolved = _resolveSurvivorCoord(t);
      if (!resolved) return;
      const id = String(t.id);
      const coord = [resolved.lon, resolved.lat];
      t = { ...t, lat: resolved.lat, lon: resolved.lon };
      const prob = t.probability_pct ?? Math.round((t.confidence || 0) * 100);
      const isConfirmed = t.confirmed || confirmedSurvivorStore[id];

      if (isConfirmed && placedSurvivorMarkers[id]) {
        placedSurvivorMarkers[id].remove();
        delete placedSurvivorMarkers[id];
      }

      const popupHtml = (
        `<strong>Survivor #${id}</strong> ${isConfirmed ? "— FOUND" : "— scanning"}<br/>`
        + `Probability: ${prob}%<br/>`
        + `Resp: ${t.respiration_bpm ? Math.round(t.respiration_bpm) : "—"} BPM<br/>`
        + `${t.lat.toFixed(6)}, ${t.lon.toFixed(6)}`
      );

      if (!survivorMarkers[id]) {
        const el = document.createElement("div");
        el.className = isConfirmed ? "survivor-pin confirmed" : "survivor-pin scanning";
        el.innerHTML = isConfirmed
          ? `<div class="pin-dot">${id}</div>`
          : `<div class="pin-dot scan">${prob}%</div>`;
        el.title = isConfirmed ? `Survivor #${id} found — ${prob}%` : `Scanning — ${prob}%`;
        survivorMarkers[id] = makeMarker(el, coord, "bottom")
          .setPopup(new maplibregl.Popup({ offset: 12, closeButton: false, anchor: "bottom" }).setHTML(popupHtml));
      } else {
        survivorMarkers[id].setLngLat(coord);
        const el = survivorMarkers[id].getElement();
        if (isConfirmed) {
          el.className = "survivor-pin confirmed";
          el.innerHTML = `<div class="pin-dot">${id}</div>`;
          el.title = `Survivor #${id} found — ${prob}%`;
        }
      }
    });

    map.getSource("confirmed-survivors")?.setData({ type: "FeatureCollection", features: [] });
    map.getSource("survivor-pulse").setData({
      type: "FeatureCollection",
      features: all.filter((t) => t.lat != null && !t.confirmed && !(t.probability_pct >= 55)).map((t) => ({
        type: "Feature",
        geometry: { type: "Point", coordinates: [t.lon, t.lat] },
        properties: { prob: t.probability_pct || 0 },
      })),
    });
  }

  function updateWifiSignals(signals) {
    if (!mapReady) return;
    const beams = [];
    const zones = [];
    (signals || []).forEach((s) => {
      if (s.lat == null || s.lon == null || (s.strength || 0) < 0.06) return;
      const len = 0.00008 * (s.strength || 0.5);
      const endLon = s.lon + Math.cos(s.bearing_rad || 0) * len;
      const endLat = s.lat + Math.sin(s.bearing_rad || 0) * len;
      beams.push({
        type: "Feature",
        geometry: { type: "LineString", coordinates: [[s.lon, s.lat], [endLon, endLat]] },
        properties: { strength: s.strength },
      });
      zones.push({
        type: "Feature",
        geometry: { type: "Point", coordinates: [s.lon, s.lat] },
        properties: { strength: s.strength },
      });
    });
    map.getSource("wifi-beams")?.setData({ type: "FeatureCollection", features: beams });
    map.getSource("wifi-zones")?.setData({ type: "FeatureCollection", features: zones });
  }

  function showMissionZone(msg) {
    const ring = msg?.geo?.zone_polygon_geo || msg?.zone?.polygon_geo;
    if (ring && ring.length >= 3) {
      const shouldFit = !missionActive && !zoneFitted;
      _setZone(ring, shouldFit);
      if (shouldFit) zoneFitted = true;
    }
  }

  function resize() {
    map?.resize();
  }

  return {
    init,
    flyTo,
    getAnchor,
    setDrawMode,
    clearDraw,
    clearMissionVisuals,
    clearMissionSurvivors,
    setMissionSurvivors,
    setMissionActive,
    closePolygon,
    getZoneGeo,
    setSurvivorMode,
    clearPlacedSurvivors,
    getPlacedSurvivors,
    updateUnits,
    updateSurvivors,
    updateWifiSignals,
    showMissionZone,
    fitToZone,
    fitToUnits,
    resize,
    set onZoneChange(cb) { onZoneChange = cb; },
    set onSurvivorChange(cb) { onSurvivorChange = cb; },
  };
})();
