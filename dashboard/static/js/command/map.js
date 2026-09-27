/* MapLibre real-world 3D SAR map */

const AuraMap = (function () {
  let map = null;
  let drawPts = [];
  let drawMode = false;
  let anchor = null;
  let onZoneChange = null;

  const STYLE = "https://tiles.openfreemap.org/styles/liberty";

  function init(containerId) {
    map = new maplibregl.Map({
      container: containerId,
      style: STYLE,
      center: [-122.1661, 37.4241],
      zoom: 15,
      pitch: 55,
      bearing: -18,
      antialias: true,
    });

    map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), "top-right");

    map.on("load", () => {
      _ensureLayers();
      if (map.getLayer("building-3d")) {
        map.setLayoutProperty("building-3d", "visibility", "visible");
      }
    });

    map.on("click", (e) => {
      if (!drawMode) return;
      drawPts.push([e.lngLat.lng, e.lngLat.lat]);
      _renderDraw();
      if (onZoneChange) onZoneChange(drawPts.slice());
    });

    return map;
  }

  function _ensureLayers() {
    const sources = ["zone-fill", "zone-line", "draw-line", "units", "survivors", "coverage"];
    sources.forEach((id) => {
      if (!map.getSource(id)) {
        if (id === "zone-fill") {
          map.addSource(id, { type: "geojson", data: { type: "FeatureCollection", features: [] } });
          map.addLayer({
            id: `${id}-layer`,
            type: "fill",
            source: id,
            paint: { "fill-color": "#f59e0b", "fill-opacity": 0.18 },
          });
        } else if (id === "zone-line" || id === "draw-line") {
          map.addSource(id, { type: "geojson", data: { type: "Feature", geometry: { type: "LineString", coordinates: [] } } });
          map.addLayer({
            id: `${id}-layer`,
            type: "line",
            source: id,
            paint: { "line-color": id === "zone-line" ? "#fbbf24" : "#0ea5e9", "line-width": 2.5 },
          });
        } else if (id === "units") {
          map.addSource(id, { type: "geojson", data: { type: "FeatureCollection", features: [] } });
          map.addLayer({
            id: "units-spider",
            type: "circle",
            source: id,
            filter: ["==", ["get", "kind"], "spiderbot"],
            paint: {
              "circle-radius": 9,
              "circle-color": "#0ea5e9",
              "circle-stroke-width": 2,
              "circle-stroke-color": "#e0f2fe",
            },
          });
          map.addLayer({
            id: "units-drone",
            type: "circle",
            source: id,
            filter: ["==", ["get", "kind"], "drone"],
            paint: {
              "circle-radius": 8,
              "circle-color": "#22c55e",
              "circle-stroke-width": 2,
              "circle-stroke-color": "#dcfce7",
            },
          });
          map.addLayer({
            id: "units-label",
            type: "symbol",
            source: id,
            layout: {
              "text-field": ["get", "name"],
              "text-size": 11,
              "text-offset": [0, 1.4],
              "text-anchor": "top",
            },
            paint: { "text-color": "#e8eef4" },
          });
        } else if (id === "survivors") {
          map.addSource(id, { type: "geojson", data: { type: "FeatureCollection", features: [] } });
          map.addLayer({
            id: "survivors-pulse",
            type: "circle",
            source: id,
            paint: {
              "circle-radius": ["+", 10, ["*", ["get", "prob"], 0.08]],
              "circle-color": "#ef4444",
              "circle-opacity": 0.35,
              "circle-blur": 0.6,
            },
          });
          map.addLayer({
            id: "survivors-core",
            type: "circle",
            source: id,
            paint: {
              "circle-radius": 7,
              "circle-color": "#ef4444",
              "circle-stroke-width": 2,
              "circle-stroke-color": "#fecaca",
            },
          });
        } else if (id === "coverage") {
          map.addSource(id, { type: "geojson", data: { type: "FeatureCollection", features: [] } });
          map.addLayer({
            id: "coverage-layer",
            type: "line",
            source: id,
            paint: { "line-color": "#38bdf8", "line-width": 1.5, "line-opacity": 0.45 },
          });
        }
      }
    });
  }

  function flyTo(lat, lon, label) {
    anchor = { lat, lon, label };
    map.flyTo({ center: [lon, lat], zoom: 16, pitch: 58, duration: 1800 });
  }

  function getAnchor() {
    return anchor;
  }

  function setDrawMode(on) {
    drawMode = on;
    map.getCanvas().style.cursor = on ? "crosshair" : "";
  }

  function clearDraw() {
    drawPts = [];
    _renderDraw();
    if (onZoneChange) onZoneChange([]);
  }

  function closePolygon() {
    if (drawPts.length < 3) return null;
    const ring = drawPts.slice();
    _setZone(ring);
    drawPts = [];
    _renderDraw();
    return ring;
  }

  function _renderDraw() {
    if (!map || !map.getSource("draw-line")) return;
    const coords = drawPts.length ? drawPts : [];
    map.getSource("draw-line").setData({
      type: "Feature",
      geometry: { type: "LineString", coordinates: coords },
    });
    if (drawPts.length >= 3) {
      map.getSource("zone-fill").setData({
        type: "FeatureCollection",
        features: [{
          type: "Feature",
          geometry: { type: "Polygon", coordinates: [[...drawPts, drawPts[0]]] },
        }],
      });
    }
  }

  function _setZone(ring) {
    if (!map || !map.getSource("zone-line")) return;
    map.getSource("zone-line").setData({
      type: "Feature",
      geometry: { type: "LineString", coordinates: [...ring, ring[0]] },
    });
    map.getSource("zone-fill").setData({
      type: "FeatureCollection",
      features: [{
        type: "Feature",
        geometry: { type: "Polygon", coordinates: [[...ring, ring[0]]] },
      }],
    });
  }

  function getZoneGeo() {
    return drawPts.length >= 3 ? drawPts.slice() : null;
  }

  function updateUnits(units) {
    if (!map || !map.getSource("units")) return;
    const features = (units || []).filter((u) => u.lat != null && u.lon != null).map((u) => ({
      type: "Feature",
      geometry: {
        type: "Point",
        coordinates: [u.lon, u.lat],
      },
      properties: {
        id: u.id,
        name: u.name,
        kind: u.type,
        status: u.status,
      },
    }));
    map.getSource("units").setData({ type: "FeatureCollection", features });
  }

  function updateSurvivors(targets) {
    if (!map || !map.getSource("survivors")) return;
    const features = (targets || []).filter((t) => t.lat != null && t.lon != null).map((t) => ({
      type: "Feature",
      geometry: { type: "Point", coordinates: [t.lon, t.lat] },
      properties: {
        id: t.id,
        prob: t.probability_pct || Math.round((t.confidence || 0) * 100),
        resp: t.respiration_bpm || 0,
        vitals: t.vitals_confidence_pct || 0,
        triage: t.suggested_triage || "assessing",
      },
    }));
    map.getSource("survivors").setData({ type: "FeatureCollection", features });
  }

  function showMissionZone(msg) {
    const ring = msg?.geo?.zone_polygon_geo || msg?.zone?.polygon_geo;
    if (ring && ring.length >= 3) _setZone(ring);
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
    set onZoneChange(cb) { onZoneChange = cb; },
  };
})();
