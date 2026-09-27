/* GSAP scroll-driven fleet stage: spiderbot → drone → command */

(function () {
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (reduced || typeof gsap === "undefined" || typeof ScrollTrigger === "undefined") {
    document.querySelectorAll(".fleet-slide").forEach((el) => {
      el.style.opacity = "1";
      el.style.pointerEvents = "auto";
    });
    return;
  }

  gsap.registerPlugin(ScrollTrigger);

  const stage = document.querySelector(".fleet-stage");
  const pin = document.querySelector(".fleet-pin");
  const progressBar = document.querySelector(".fleet-progress-bar");
  const slideSpider = document.querySelector(".fleet-slide-spider");
  const slideDrone = document.querySelector(".fleet-slide-drone");
  const slideCommand = document.querySelector(".fleet-slide-command");

  if (!stage || !pin || !slideSpider || !slideDrone || !slideCommand) return;

  const tl = gsap.timeline({
    scrollTrigger: {
      trigger: stage,
      start: "top top",
      end: "bottom bottom",
      scrub: 1,
      pin: pin,
      anticipatePin: 1,
      onUpdate: (self) => {
        if (progressBar) progressBar.style.width = `${self.progress * 100}%`;
      },
    },
  });

  tl
    .to(slideSpider, { opacity: 1, scale: 1, duration: 0.15 }, 0)
    .to(slideSpider, {
      opacity: 0,
      scale: 0.92,
      y: -40,
      duration: 0.25,
      ease: "power2.in",
    }, 0.28)
    .fromTo(
      slideDrone,
      { opacity: 0, scale: 0.88, y: 60 },
      { opacity: 1, scale: 1, y: 0, duration: 0.3, ease: "power2.out" },
      0.32
    )
    .to(slideDrone, {
      opacity: 0,
      scale: 0.94,
      y: -30,
      duration: 0.25,
      ease: "power2.in",
    }, 0.62)
    .fromTo(
      slideCommand,
      { opacity: 0, scale: 0.9, y: 50 },
      { opacity: 1, scale: 1, y: 0, duration: 0.3, ease: "power2.out" },
      0.66
    )
    .to(slideCommand, { opacity: 1, duration: 0.2 }, 0.95);

  gsap.set(slideDrone, { opacity: 0, pointerEvents: "none" });
  gsap.set(slideCommand, { opacity: 0, pointerEvents: "none" });

  tl.eventCallback("onUpdate", () => {
    const p = tl.progress();
    slideSpider.style.pointerEvents = p < 0.35 ? "auto" : "none";
    slideDrone.style.pointerEvents = p >= 0.35 && p < 0.68 ? "auto" : "none";
    slideCommand.style.pointerEvents = p >= 0.68 ? "auto" : "none";
  });

  gsap.utils.toArray(".section h2, .problem-card, .step, .metric-tile").forEach((el) => {
    gsap.from(el, {
      opacity: 0,
      y: 28,
      duration: 0.7,
      ease: [0.16, 1, 0.3, 1],
      scrollTrigger: {
        trigger: el,
        start: "top 88%",
        toggleActions: "play none none none",
      },
    });
  });

  window.addEventListener("load", () => ScrollTrigger.refresh());
})();
