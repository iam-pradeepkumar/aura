/* MapLibre full-screen SAR map with reliable polygon draw + live unit markers */

const AuraMap = (function () {
  let map = null;
  let mapReady = false;
  let drawPts = [];
  let closedZone = [];
  let drawMode = false;
  let anchor = null;
  let onZoneChange = null;

  const unitMarkers = {};
  const survivorMarkers = {};
  const vertexMarkers = [];
  const trails = {};
  let clickTimer = null;
  const STYLE = "https://tiles.openfreemap.org/styles/liberty";

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
    });

    map.on("click", (e) => {
      if (!drawMode || !mapReady) return;
      if (clickTimer) clearTimeout(clickTimer);
      clickTimer = setTimeout(() => {
        clickTimer = null;
        const pt = [e.lngLat.lng, e.lngLat.lat];
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
        "circle-radius": 22,
        "circle-color": "#ef4444",
        "circle-opacity": 0.25,
        "circle-blur": 0.5,
      },
    });

    map.addSource("units-dots", { type: "geojson", data: emptyFC() });
    map.addLayer({
      id: "units-dots-layer",
      type: "circle",
      source: "units-dots",
      paint: {
        "circle-radius": 10,
        "circle-color": ["get", "color"],
        "circle-stroke-width": 2,
        "circle-stroke-color": "#ffffff",
        "circle-pitch-alignment": "viewport",
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
    const m = new maplibregl.Marker({ element: el, anchor: "center" })
      .setLngLat(coord)
      .addTo(map);
    vertexMarkers.push(m);
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

  function _setZone(ring) {
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
    fitToZone(ring);
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

  function setDrawMode(on) {
    drawMode = on;
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

  function clearDraw() {
    drawPts = [];
    closedZone = [];
    _clearVertices();
    if (mapReady) {
      map.getSource("draw-line")?.setData(emptyLine());
      map.getSource("zone-fill")?.setData(emptyFC());
      map.getSource("zone-line")?.setData(emptyLine());
      map.getSource("trails")?.setData(emptyFC());
    }
    Object.values(unitMarkers).forEach((m) => m.remove());
    Object.values(survivorMarkers).forEach((m) => m.remove());
    Object.keys(unitMarkers).forEach((k) => delete unitMarkers[k]);
    Object.keys(survivorMarkers).forEach((k) => delete survivorMarkers[k]);
    Object.keys(trails).forEach((k) => delete trails[k]);
    if (onZoneChange) onZoneChange([]);
  }

  function closePolygon() {
    if (drawPts.length < 3) return null;
    const ring = drawPts.slice();
    _setZone(ring);
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
    if (!last || Math.hypot(last[0] - coord[0], last[1] - coord[1]) > 0.000008) {
      trails[id].push(coord);
      if (trails[id].length > 120) trails[id].shift();
    }

    if (!unitMarkers[id]) {
      const el = document.createElement("div");
      el.className = `unit-marker ${u.type === "drone" ? "drone" : "spider"}`;
      el.innerHTML = `<div class="icon">${u.type === "drone" ? "DR" : "SP"}</div><div class="lbl">${u.name || id}</div>`;
      unitMarkers[id] = new maplibregl.Marker({ element: el, anchor: "bottom" })
        .setLngLat(coord)
        .addTo(map);
    } else {
      unitMarkers[id].setLngLat(coord);
      const lbl = unitMarkers[id].getElement().querySelector(".lbl");
      if (lbl) lbl.textContent = u.name || id;
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

  function updateSurvivors(targets) {
    if (!mapReady) return;
    const ids = new Set();
    (targets || []).forEach((t) => {
      if (t.lat == null || t.lon == null) return;
      const id = String(t.id);
      ids.add(id);
      const coord = [t.lon, t.lat];
      const prob = t.probability_pct ?? Math.round((t.confidence || 0) * 100);

      if (!survivorMarkers[id]) {
        const el = document.createElement("div");
        el.className = "survivor-marker";
        el.title = `Survivor #${id} — ${prob}% probability`;
        survivorMarkers[id] = new maplibregl.Marker({ element: el })
          .setLngLat(coord)
          .setPopup(new maplibregl.Popup({ offset: 12 }).setHTML(
            `<strong>Survivor #${id}</strong><br/>Probability: ${prob}%<br/>`
            + `Resp: ${t.respiration_bpm ? Math.round(t.respiration_bpm) : "—"} BPM<br/>`
            + `Vitals conf: ${t.vitals_confidence_pct ?? 0}%`
          ))
          .addTo(map);
      } else {
        survivorMarkers[id].setLngLat(coord);
      }
    });

    map.getSource("survivor-pulse").setData({
      type: "FeatureCollection",
      features: (targets || []).filter((t) => t.lat != null).map((t) => ({
        type: "Feature",
        geometry: { type: "Point", coordinates: [t.lon, t.lat] },
        properties: { prob: t.probability_pct || 0 },
      })),
    });
  }

  function showMissionZone(msg) {
    const ring = msg?.geo?.zone_polygon_geo || msg?.zone?.polygon_geo;
    if (ring && ring.length >= 3) _setZone(ring);
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
    closePolygon,
    getZoneGeo,
    updateUnits,
    updateSurvivors,
    showMissionZone,
    fitToZone,
    fitToUnits,
    resize,
    set onZoneChange(cb) { onZoneChange = cb; },
  };
})();
