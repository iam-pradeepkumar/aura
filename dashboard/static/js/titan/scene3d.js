/* AURA TITAN — Three.js disaster zone scene */

const TITANScene = (function () {
  let scene, camera, renderer, controls;
  let zoneMesh, obstacleMeshes = [], unitMeshes = {}, survivorMeshes = {};
  let raycaster, mouse, groundPlane;
  let polygonPoints = [];
  let polygonLine = null;
  let drawMode = false;
  let areaSize = 40;
  let onPolygonPoint = null;

  function init(container) {
    scene = new THREE.Scene();
    scene.background = new THREE.Color(0x02070a);
    scene.fog = new THREE.Fog(0x02070a, 20, 55);

    const w = container.clientWidth;
    const h = container.clientHeight;
    camera = new THREE.PerspectiveCamera(45, w / h, 0.1, 200);
    camera.position.set(25, 22, 25);
    camera.lookAt(areaSize / 2, 0, areaSize / 2);

    renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setSize(w, h);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    container.appendChild(renderer.domElement);

    controls = new THREE.OrbitControls(camera, renderer.domElement);
    controls.target.set(areaSize / 2, 0, areaSize / 2);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.maxPolarAngle = Math.PI / 2.1;
    controls.minDistance = 8;
    controls.maxDistance = 60;

    scene.add(new THREE.AmbientLight(0x334455, 0.6));
    const sun = new THREE.DirectionalLight(0x38bdf8, 0.5);
    sun.position.set(20, 30, 10);
    scene.add(sun);

    const grid = new THREE.GridHelper(areaSize, areaSize, 0x1a3a4a, 0x0d1f28);
    grid.position.set(areaSize / 2, 0.01, areaSize / 2);
    scene.add(grid);

    groundPlane = new THREE.Mesh(
      new THREE.PlaneGeometry(areaSize, areaSize),
      new THREE.MeshBasicMaterial({ visible: false })
    );
    groundPlane.rotation.x = -Math.PI / 2;
    groundPlane.position.set(areaSize / 2, 0, areaSize / 2);
    scene.add(groundPlane);

    raycaster = new THREE.Raycaster();
    mouse = new THREE.Vector2();

    renderer.domElement.addEventListener("click", onClick);
    window.addEventListener("resize", onResize);
    animate();
  }

  function onResize() {
    const c = renderer.domElement.parentElement;
    if (!c) return;
    camera.aspect = c.clientWidth / c.clientHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(c.clientWidth, c.clientHeight);
  }

  function onClick(ev) {
    if (!drawMode) return;
    const rect = renderer.domElement.getBoundingClientRect();
    mouse.x = ((ev.clientX - rect.left) / rect.width) * 2 - 1;
    mouse.y = -((ev.clientY - rect.top) / rect.height) * 2 + 1;
    raycaster.setFromCamera(mouse, camera);
    const hits = raycaster.intersectObject(groundPlane);
    if (hits.length) {
      const p = hits[0].point;
      polygonPoints.push([Math.round(p.x * 10) / 10, Math.round(p.z * 10) / 10]);
      updatePolygonVisual();
      if (onPolygonPoint) onPolygonPoint(polygonPoints);
    }
  }

  function updatePolygonVisual() {
    if (polygonLine) scene.remove(polygonLine);
    if (polygonPoints.length < 2) return;
    const pts = polygonPoints.map(([x, y]) => new THREE.Vector3(x, 0.15, y));
    if (polygonPoints.length >= 3) pts.push(pts[0].clone());
    const geo = new THREE.BufferGeometry().setFromPoints(pts);
    polygonLine = new THREE.Line(
      geo,
      new THREE.LineBasicMaterial({ color: 0xfbbf24, linewidth: 2 })
    );
    scene.add(polygonLine);
  }

  function setZonePolygon(pts) {
    polygonPoints = pts.map((p) => [p[0], p[1]]);
    updatePolygonVisual();
    if (zoneMesh) scene.remove(zoneMesh);
    if (pts.length < 3) return;
    const shape = new THREE.Shape();
    shape.moveTo(pts[0][0], pts[0][1]);
    for (let i = 1; i < pts.length; i++) shape.lineTo(pts[i][0], pts[i][1]);
    shape.closePath();
    const geo = new THREE.ShapeGeometry(shape);
    zoneMesh = new THREE.Mesh(
      geo,
      new THREE.MeshBasicMaterial({ color: 0xfbbf24, transparent: true, opacity: 0.08, side: THREE.DoubleSide })
    );
    zoneMesh.rotation.x = -Math.PI / 2;
    zoneMesh.position.y = 0.05;
    scene.add(zoneMesh);
  }

  function setObstacles(obs) {
    obstacleMeshes.forEach((m) => scene.remove(m));
    obstacleMeshes = [];
    (obs || []).forEach((o) => {
      const r = o.radius || o[2] || 1;
      const x = o.x ?? o[0];
      const y = o.y ?? o[1];
      const mesh = new THREE.Mesh(
        new THREE.CylinderGeometry(r, r * 0.9, r * 0.8, 12),
        new THREE.MeshStandardMaterial({ color: 0x5a5048, roughness: 0.9 })
      );
      mesh.position.set(x, r * 0.4, y);
      scene.add(mesh);
      obstacleMeshes.push(mesh);
    });
  }

  function upsertUnit(u) {
    const id = u.id;
    if (unitMeshes[id]) scene.remove(unitMeshes[id]);
    const group = new THREE.Group();
    if (u.type === "drone") {
      const body = new THREE.Mesh(
        new THREE.BoxGeometry(0.8, 0.2, 0.8),
        new THREE.MeshStandardMaterial({ color: 0x4ade80, emissive: 0x1a4030 })
      );
      group.add(body);
      const alt = u.z || 6;
      group.position.set(u.x || 0, alt, u.y || 0);
    } else {
      const body = new THREE.Mesh(
        new THREE.BoxGeometry(0.7, 0.35, 0.9),
        new THREE.MeshStandardMaterial({ color: 0x38bdf8, emissive: 0x0a2840 })
      );
      body.position.y = 0.2;
      group.add(body);
      for (let i = 0; i < 4; i++) {
        const leg = new THREE.Mesh(
          new THREE.CylinderGeometry(0.04, 0.04, 0.25),
          new THREE.MeshStandardMaterial({ color: 0x8899aa })
        );
        leg.position.set((i < 2 ? -0.25 : 0.25), 0.05, (i % 2 === 0 ? -0.3 : 0.3));
        group.add(leg);
      }
      group.position.set(u.x || 0, 0, u.y || 0);
    }
    scene.add(group);
    unitMeshes[id] = group;
  }

  function upsertSurvivor(t) {
    const id = String(t.id);
    if (survivorMeshes[id]) scene.remove(survivorMeshes[id]);
    const prob = t.probability_pct || (t.confidence || 0) * 100;
    const mesh = new THREE.Mesh(
      new THREE.SphereGeometry(0.35 + prob / 200, 16, 16),
      new THREE.MeshStandardMaterial({
        color: 0xf87171,
        emissive: 0x501010,
        transparent: true,
        opacity: 0.85,
      })
    );
    mesh.position.set(t.x_m, 0.4, t.y_m);
    scene.add(mesh);
    survivorMeshes[id] = mesh;
  }

  function clearSurvivors() {
    Object.values(survivorMeshes).forEach((m) => scene.remove(m));
    survivorMeshes = {};
  }

  function setDrawMode(on) {
    drawMode = on;
  }

  function clearPolygon() {
    polygonPoints = [];
    if (polygonLine) { scene.remove(polygonLine); polygonLine = null; }
    if (zoneMesh) { scene.remove(zoneMesh); zoneMesh = null; }
  }

  function getPolygon() {
    return polygonPoints.slice();
  }

  function animate() {
    requestAnimationFrame(animate);
    controls.update();
    Object.values(survivorMeshes).forEach((m, i) => {
      m.position.y = 0.4 + Math.sin(Date.now() * 0.003 + i) * 0.08;
    });
    renderer.render(scene, camera);
  }

  return {
    init,
    setZonePolygon,
    setObstacles,
    upsertUnit,
    upsertSurvivor,
    clearSurvivors,
    setDrawMode,
    clearPolygon,
    getPolygon,
    set onPolygonPoint(cb) { onPolygonPoint = cb; },
    set areaSize(v) { areaSize = v; },
  };
})();
