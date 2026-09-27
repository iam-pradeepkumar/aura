/* Three.js 3D spiderbot + drone models on MapLibre custom layer */

const AuraScene3D = (function () {
  let map = null;
  let layerAdded = false;
  const units = {};
  let scene, camera, renderer, root;

  function _makeSpider() {
    const g = new THREE.Group();
    const body = new THREE.Mesh(
      new THREE.BoxGeometry(0.55, 0.22, 0.75),
      new THREE.MeshStandardMaterial({ color: 0x0ea5e9, metalness: 0.55, roughness: 0.35 })
    );
    body.position.y = 0.18;
    g.add(body);
    const matLeg = new THREE.MeshStandardMaterial({ color: 0x0369a1, metalness: 0.4, roughness: 0.5 });
    [[-0.28, -0.28], [0.28, -0.28], [-0.28, 0.28], [0.28, 0.28]].forEach(([lx, ly]) => {
      const leg = new THREE.Mesh(new THREE.CylinderGeometry(0.04, 0.05, 0.35, 6), matLeg);
      leg.position.set(lx, 0.08, ly);
      leg.rotation.x = Math.PI / 2.2;
      g.add(leg);
    });
    const antenna = new THREE.Mesh(
      new THREE.CylinderGeometry(0.02, 0.02, 0.45, 6),
      new THREE.MeshStandardMaterial({ color: 0xfbbf24, emissive: 0xf59e0b, emissiveIntensity: 0.35 })
    );
    antenna.position.set(0, 0.48, 0);
    g.add(antenna);
    const ring = new THREE.Mesh(
      new THREE.RingGeometry(0.35, 0.55, 32),
      new THREE.MeshBasicMaterial({ color: 0x0ea5e9, transparent: true, opacity: 0.22, side: THREE.DoubleSide })
    );
    ring.rotation.x = -Math.PI / 2;
    ring.position.y = 0.02;
    ring.name = "wifiRing";
    g.add(ring);
    g.scale.set(1.8, 1.8, 1.8);
    return g;
  }

  function _makeDrone() {
    const g = new THREE.Group();
    const body = new THREE.Mesh(
      new THREE.BoxGeometry(0.7, 0.12, 0.7),
      new THREE.MeshStandardMaterial({ color: 0x22c55e, metalness: 0.5, roughness: 0.3 })
    );
    g.add(body);
    const armMat = new THREE.MeshStandardMaterial({ color: 0x14532d, metalness: 0.35, roughness: 0.45 });
    [[-0.45, 0, -0.45], [0.45, 0, -0.45], [-0.45, 0, 0.45], [0.45, 0, 0.45]].forEach(([x, y, z]) => {
      const arm = new THREE.Mesh(new THREE.BoxGeometry(0.55, 0.04, 0.04), armMat);
      arm.position.set(x * 0.5, y, z * 0.5);
      g.add(arm);
      const prop = new THREE.Mesh(
        new THREE.CylinderGeometry(0.16, 0.16, 0.02, 16),
        new THREE.MeshStandardMaterial({ color: 0x86efac, transparent: true, opacity: 0.85 })
      );
      prop.position.set(x, 0.08, z);
      prop.name = "prop";
      g.add(prop);
    });
    g.scale.set(1.6, 1.6, 1.6);
    return g;
  }

  function attach(mapInstance) {
    map = mapInstance;
    if (layerAdded || typeof THREE === "undefined") return;
    const customLayer = {
      id: "aura-3d-units",
      type: "custom",
      renderingMode: "3d",
      onAdd(m, gl) {
        camera = new THREE.Camera();
        scene = new THREE.Scene();
        root = new THREE.Group();
        scene.add(root);
        const amb = new THREE.AmbientLight(0xffffff, 0.65);
        const dir = new THREE.DirectionalLight(0xffffff, 0.85);
        dir.position.set(80, 120, 60);
        scene.add(amb, dir);
        renderer = new THREE.WebGLRenderer({
          canvas: m.getCanvas(),
          context: gl,
          antialias: true,
        });
        renderer.autoClear = false;
      },
      render(_gl, matrix) {
        if (!renderer || !root) return;
        Object.entries(units).forEach(([id, entry]) => {
          if (!entry.mesh || entry.lng == null) return;
          const mc = maplibregl.MercatorCoordinate.fromLngLat([entry.lng, entry.lat], entry.alt);
          const scale = mc.meterInMercatorCoordinateUnits();
          const m4 = new THREE.Matrix4().fromArray(matrix);
          const l = new THREE.Matrix4()
            .makeTranslation(mc.x, mc.y, mc.z)
            .scale(new THREE.Vector3(scale, -scale, scale));
          entry.mesh.matrixAutoUpdate = false;
          entry.mesh.matrix.copy(m4.multiply(l));
          if (entry.yaw != null) {
            entry.mesh.rotation.z = -entry.yaw;
          }
          const ring = entry.mesh.getObjectByName("wifiRing");
          if (ring) {
            ring.material.opacity = 0.12 + (entry.wifi || 0) * 0.45;
            ring.scale.setScalar(1 + (entry.wifi || 0) * 0.8);
          }
          entry.mesh.children.forEach((ch) => {
            if (ch.name === "prop") ch.rotation.y += 0.35;
          });
        });
        renderer.resetState();
        renderer.render(scene, camera);
        map.triggerRepaint();
      },
    };
    const addLayer = () => {
      if (layerAdded || map.getLayer("aura-3d-units")) return;
      const before = map.getLayer("units-dots-layer") ? "units-dots-layer" : undefined;
      map.addLayer(customLayer, before);
      layerAdded = true;
    };
    if (map.loaded()) addLayer();
    else map.once("load", addLayer);
  }

  function updateUnitList(unitList) {
    if (!root || typeof THREE === "undefined") return;
    const seen = new Set();
    (unitList || []).forEach((u) => {
      if (u.lat == null || u.lon == null) return;
      seen.add(u.id);
      if (!units[u.id]) {
        const mesh = u.type === "drone" ? _makeDrone() : _makeSpider();
        root.add(mesh);
        units[u.id] = { mesh, lng: u.lon, lat: u.lat, alt: u.type === "drone" ? (u.alt_m || 12) : 0.5, yaw: u.yaw || 0, wifi: u.wifi_signal || 0 };
      } else {
        const e = units[u.id];
        e.lng = u.lon;
        e.lat = u.lat;
        e.alt = u.type === "drone" ? (u.alt_m || u.z || 12) : 0.5;
        e.yaw = u.yaw || 0;
        e.wifi = u.wifi_signal || 0;
      }
    });
    Object.keys(units).forEach((id) => {
      if (!seen.has(id)) {
        root.remove(units[id].mesh);
        delete units[id];
      }
    });
  }

  return { attach, updateUnitList };
})();
