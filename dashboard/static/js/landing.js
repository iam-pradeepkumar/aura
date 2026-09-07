(function () {
  // Gentle parallax on floating sketch cards (desktop)
  const floats = document.querySelectorAll(".float-sketch");
  if (floats.length && window.matchMedia("(min-width: 901px)").matches) {
    let raf = 0;
    window.addEventListener("mousemove", (ev) => {
      const cx = (ev.clientX / window.innerWidth - 0.5) * 2;
      const cy = (ev.clientY / window.innerHeight - 0.5) * 2;
      if (!raf) {
        raf = requestAnimationFrame(() => {
          floats.forEach((el, i) => {
            const f = 3 + i;
            const base = el.classList.contains("float-tl") ? -4
              : el.classList.contains("float-tr") ? 2
              : el.classList.contains("float-bl") ? 1.5 : -2;
            el.style.transform = `rotate(${base}deg) translate(${cx * f}px, ${cy * f}px)`;
          });
          raf = 0;
        });
      }
    });
  }

  // Stagger case cards
  document.querySelectorAll(".case-card").forEach((card, i) => {
    card.style.transitionDelay = `${0.08 * i}s`;
  });
})();
