(function () {
  const obs = new IntersectionObserver(
    (entries) => entries.forEach((e) => {
      if (e.isIntersecting) {
        e.target.classList.add("visible");
        obs.unobserve(e.target);
      }
    }),
    { threshold: 0.12, rootMargin: "0px 0px -50px 0px" }
  );
  document.querySelectorAll(".reveal-up").forEach((el) => obs.observe(el));

  // Stagger india cards on reveal
  document.querySelectorAll(".india-card").forEach((card, i) => {
    card.style.transitionDelay = `${i * 0.08}s`;
    card.classList.add("reveal-up");
    obs.observe(card);
  });

  // Parallax on floating cards (desktop)
  const wraps = document.querySelectorAll(".float-wrap");
  if (wraps.length && window.matchMedia("(min-width: 901px)").matches) {
    let raf = 0;
    let cx = 0;
    let cy = 0;

    window.addEventListener("mousemove", (ev) => {
      cx = (ev.clientX / window.innerWidth - 0.5) * 2;
      cy = (ev.clientY / window.innerHeight - 0.5) * 2;
      if (!raf) {
        raf = requestAnimationFrame(() => {
          wraps.forEach((wrap) => {
            const depth = parseFloat(wrap.dataset.depth || "6");
            const card = wrap.querySelector(".float-card");
            if (!card) return;
            const tx = cx * depth * 0.6;
            const ty = cy * depth * 0.6;
            const rx = cy * 2.5;
            const ry = cx * -2.5;
            wrap.style.transform = `translate3d(${tx}px, ${ty}px, 0) rotateX(${rx}deg) rotateY(${ry}deg)`;
          });
          raf = 0;
        });
      }
    });
  }

  // Subtle hero icon tilt on scroll
  const icon = document.querySelector(".hero-icon-3d");
  if (icon) {
    window.addEventListener("scroll", () => {
      const y = Math.min(window.scrollY / 400, 1);
      icon.style.transform = `translateY(${-y * 8}px) rotateX(${8 - y * 12}deg)`;
    }, { passive: true });
  }
})();
