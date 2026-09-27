/* Landing hero — floating spiderbot + drone Three.js scene */

(function () {
  const canvas = document.getElementById("hero-3d");
  if (!canvas || typeof THREE === "undefined") return;

  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setClearColor(0x000000, 0);

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(42, 1, 0.1, 100);
  camera.position.set(0, 2.2, 6.5);

  const amb = new THREE.AmbientLight(0xffffff, 0.55);
  const key = new THREE.DirectionalLight(0xffffff, 0.9);
  key.position.set(4, 8, 6);
  const rim = new THREE.PointLight(0x0ea5e9, 1.2, 20);
  rim.position.set(-3, 2, 2);
  scene.add(amb, key, rim);

  function makeSpider() {
    const g = new THREE.Group();
    const body = new THREE.Mesh(
      new THREE.BoxGeometry(1.1, 0.4, 1.5),
      new THREE.MeshStandardMaterial({ color: 0x0ea5e9, metalness: 0.6, roughness: 0.35 })
    );
    body.position.y = 0.35;
    g.add(body);
    const legMat = new THREE.MeshStandardMaterial({ color: 0x0369a1, metalness: 0.45, roughness: 0.5 });
    [[-0.55, -0.55], [0.55, -0.55], [-0.55, 0.55], [0.55, 0.55]].forEach(([lx, lz]) => {
      const leg = new THREE.Mesh(new THREE.CylinderGeometry(0.06, 0.08, 0.7, 6), legMat);
      leg.position.set(lx, 0.12, lz);
      leg.rotation.x = Math.PI / 2.4;
      g.add(leg);
    });
    const ring = new THREE.Mesh(
      new THREE.RingGeometry(0.7, 1.05, 32),
      new THREE.MeshBasicMaterial({ color: 0x0ea5e9, transparent: true, opacity: 0.2, side: THREE.DoubleSide })
    );
    ring.rotation.x = -Math.PI / 2;
    ring.position.y = 0.02;
    g.add(ring);
    g.position.set(-1.4, 0, 0);
    return g;
  }

  function makeDrone() {
    const g = new THREE.Group();
    const body = new THREE.Mesh(
      new THREE.BoxGeometry(1.2, 0.18, 1.2),
      new THREE.MeshStandardMaterial({ color: 0x22c55e, metalness: 0.55, roughness: 0.3 })
    );
    g.add(body);
    const armMat = new THREE.MeshStandardMaterial({ color: 0x14532d });
    const props = [];
    [[-0.75, -0.75], [0.75, -0.75], [-0.75, 0.75], [0.75, 0.75]].forEach(([x, z]) => {
      const arm = new THREE.Mesh(new THREE.BoxGeometry(0.9, 0.06, 0.06), armMat);
      arm.position.set(x * 0.5, 0, z * 0.5);
      g.add(arm);
      const prop = new THREE.Mesh(
        new THREE.CylinderGeometry(0.28, 0.28, 0.03, 16),
        new THREE.MeshStandardMaterial({ color: 0x86efac, transparent: true, opacity: 0.85 })
      );
      prop.position.set(x, 0.12, z);
      g.add(prop);
      props.push(prop);
    });
    g.position.set(1.6, 1.8, -0.4);
    g.userData.props = props;
    return g;
  }

  const spider = makeSpider();
  const drone = makeDrone();
  const grid = new THREE.GridHelper(8, 16, 0x1e3a4a, 0x0f1720);
  grid.position.y = -0.05;
  scene.add(grid, spider, drone);

  const particles = new THREE.Group();
  for (let i = 0; i < 40; i++) {
    const dot = new THREE.Mesh(
      new THREE.SphereGeometry(0.03, 8, 8),
      new THREE.MeshBasicMaterial({ color: 0x0ea5e9, transparent: true, opacity: 0.35 })
    );
    dot.position.set((Math.random() - 0.5) * 6, Math.random() * 3, (Math.random() - 0.5) * 4);
    particles.add(dot);
  }
  scene.add(particles);

  function resize() {
    const w = canvas.clientWidth;
    const h = canvas.clientHeight;
    if (!w || !h) return;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  }

  resize();
  window.addEventListener("resize", resize);

  let t0 = performance.now();
  function tick(now) {
    const t = (now - t0) * 0.001;
    spider.rotation.y = Math.sin(t * 0.4) * 0.35;
    spider.position.y = Math.sin(t * 0.8) * 0.08;
    drone.position.y = 1.8 + Math.sin(t * 0.6 + 1) * 0.25;
    drone.rotation.y = t * 0.25;
    (drone.userData.props || []).forEach((p) => { p.rotation.y += 0.2; });
    particles.children.forEach((p, i) => {
      p.position.y += Math.sin(t + i) * 0.0008;
    });
    camera.position.x = Math.sin(t * 0.15) * 0.6;
    camera.lookAt(0, 0.6, 0);
    renderer.render(scene, camera);
    requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
})();
