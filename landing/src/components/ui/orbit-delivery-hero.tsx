"use client";

import { ArrowRight, Pause, Play, Radar, Radio } from "lucide-react";
import {
  Component,
  Suspense,
  lazy,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { Button } from "@/components/ui/button";
import { createMotion, type MotionState } from "@/components/landing/motion";
import { cn } from "@/lib/utils";

const SarPlanetScene = lazy(() =>
  import("@/components/landing/SarPlanetScene").then((m) => ({
    default: m.SarPlanetScene,
  })),
);

const stories: Record<string, { title: string; paragraphs: string[] }> = {
  Problem: {
    title: "The golden hour is lost in rubble.",
    paragraphs: [
      "After earthquakes and building collapses, survivors are buried where GPS fails, cameras cannot see, and human teams cannot safely enter.",
      "Urban search and rescue needs autonomous eyes underground and in the air — before the window for rescue closes.",
    ],
  },
  Solution: {
    title: "AURA fuses WiFi CSI with a mixed fleet.",
    paragraphs: [
      "Spiderbots crawl through voids while quadrotor drones map the disaster zone from above. WiFi Channel State Information detects micro-movements of survivors through debris.",
      "The Command Center coordinates autonomous search patterns, survivor confirmation, and live telemetry in one tactical view.",
    ],
  },
  Feasibility: {
    title: "Built for simulation today, Isaac Sim tomorrow.",
    paragraphs: [
      "The dashboard runs a full mission loop with geo-anchored units, survivor pins, and fleet telemetry — ready to swap simulated feeds for Isaac Sim and live hardware.",
      "Render-hosted deployment means every push to main updates the public demo your team can share with judges and partners.",
    ],
  },
};

type OrbitDeliveryHeroProps = {
  theme?: "auto" | "light" | "dark";
  commandHref?: string;
};

class SceneBoundary extends Component<
  { children: ReactNode },
  { failed: boolean }
> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error: unknown) {
    console.error("3D scene failed:", error);
  }

  render() {
    if (this.state.failed) {
      return (
        <div className="absolute inset-[35%_18%] z-10 text-center text-sm text-muted">
          <p className="mb-4">Could not load the rescue scene.</p>
          <Button type="button" onClick={() => location.reload()}>
            Try again
          </Button>
        </div>
      );
    }
    return this.props.children;
  }
}

export default function OrbitDeliveryHero({
  theme = "dark",
  commandHref = "/command",
}: OrbitDeliveryHeroProps) {
  const motion = useRef<MotionState>(createMotion());
  const interaction = useRef<HTMLDivElement>(null);
  const drag = useRef<{ id: number; x: number; y: number } | null>(null);

  const [visible, setVisible] = useState(true);
  const [tabVisible, setTabVisible] = useState(true);
  const [reduced, setReduced] = useState(false);
  const [sceneMounted, setSceneMounted] = useState(false);
  const [auto, setAuto] = useState(true);
  const [dragging, setDragging] = useState(false);
  const [ready, setReady] = useState(false);
  const [story, setStory] = useState<string | null>(null);

  useEffect(() => {
    setTabVisible(!document.hidden);
    const query = matchMedia("(prefers-reduced-motion: reduce)");
    const onChange = () => setReduced(query.matches);
    onChange();
    query.addEventListener("change", onChange);

    const onVisibility = () => {
      setTabVisible(!document.hidden);
      if (document.hidden) {
        motion.current.dragging = false;
        drag.current = null;
        setDragging(false);
      }
    };
    document.addEventListener("visibilitychange", onVisibility);

    const observer = new IntersectionObserver(
      ([entry]) => setVisible(entry.isIntersecting),
      { threshold: 0.01 },
    );
    if (interaction.current) observer.observe(interaction.current);

    let frame = 0;
    let timeout = 0;
    frame = requestAnimationFrame(() => {
      frame = requestAnimationFrame(() => {
        timeout = window.setTimeout(() => setSceneMounted(true), 80);
      });
    });

    return () => {
      query.removeEventListener("change", onChange);
      document.removeEventListener("visibilitychange", onVisibility);
      observer.disconnect();
      cancelAnimationFrame(frame);
      clearTimeout(timeout);
    };
  }, []);

  const release = (id: number) => {
    if (drag.current?.id !== id) return;
    drag.current = null;
    motion.current.dragging = false;
    motion.current.lastInteraction = motion.current.time;
    setDragging(false);
  };

  const toggleMotion = () => {
    const next = !auto;
    setAuto(next);
    const m = motion.current;
    m.dragging = false;
    if (
      drag.current &&
      interaction.current?.hasPointerCapture(drag.current.id)
    ) {
      interaction.current.releasePointerCapture(drag.current.id);
    }
    drag.current = null;
    setDragging(false);
    m.planetVelocity = 0;
    m.pitchVelocity = 0;
    m.dragTarget = m.planetAngle;
    m.pitchTarget = m.pitchAngle;
    if (next) m.lastInteraction = m.time - 4;
  };

  const nudge = (direction: number) => {
    if (!auto) return;
    motion.current.planetVelocity += direction * 0.65;
    motion.current.lastInteraction = motion.current.time;
  };

  const explore = () => {
    interaction.current?.focus({ preventScroll: true });
    if (window.innerWidth < 760) {
      interaction.current?.scrollIntoView({
        behavior: reduced ? "instant" : "smooth",
        block: "center",
      });
    }
    if (!reduced) nudge(1);
  };

  return (
    <div
      className="orbit-delivery relative isolate min-h-[100svh] overflow-hidden bg-[radial-gradient(ellipse_at_8%_12%,#121a2b_0%,#080d18_42%,#060a12_100%)] text-foreground"
      data-theme={theme}
    >
      <header className="relative z-20 flex h-[88px] shrink-0 items-center justify-between px-[5%] md:px-[6.5%]">
        <a href="/" className="flex items-center gap-3 font-semibold tracking-tight">
          <span className="flex size-9 items-center justify-center rounded-full bg-accent/15 ring-1 ring-accent/40">
            <Radar className="size-5 text-accent" aria-hidden />
          </span>
          <span className="flex flex-col leading-none">
            <span className="text-lg md:text-xl">AURA</span>
            <span className="mt-1 font-mono text-[9px] uppercase tracking-[0.28em] text-muted">
              Search &amp; Rescue
            </span>
          </span>
        </a>

        <nav
          className="absolute left-1/2 hidden -translate-x-1/2 items-center gap-8 md:flex"
          aria-label="Main navigation"
        >
          <button
            type="button"
            className="text-sm text-muted transition-colors hover:text-foreground"
            onClick={explore}
          >
            Mission
          </button>
          {Object.keys(stories).map((item) => (
            <button
              key={item}
              type="button"
              className="text-sm text-muted transition-colors hover:text-foreground"
              onClick={() => setStory(item)}
            >
              {item}
            </button>
          ))}
        </nav>

        <Button asChild size="sm" className="hidden sm:inline-flex">
          <a href={commandHref}>Launch Command Center</a>
        </Button>
      </header>

      <main className="relative flex min-h-0 flex-1 flex-col">
        <section
          className="relative grid min-h-[calc(100svh-88px)] grid-cols-1 lg:grid-cols-[minmax(0,46%)_1fr]"
          aria-labelledby="hero-title"
        >
          <div className="relative z-10 flex flex-col justify-center px-[5%] pb-8 pt-6 md:px-[6.5%] md:pb-0 md:pt-0 lg:pr-4">
            <p className="mb-4 font-mono text-[11px] uppercase tracking-[0.32em] text-accent">
              Golden hour autonomy
            </p>
            <h1
              id="hero-title"
              className="mb-5 max-w-xl text-[clamp(2.75rem,6vw,4.75rem)] font-semibold leading-[1.02] tracking-[-0.04em]"
            >
              Find survivors
              <br />
              <span className="text-accent">before time</span>
              <br />
              runs out.
            </h1>
            <p className="mb-8 max-w-md text-base leading-relaxed text-muted md:text-lg">
              Autonomous spiderbots, quadrotor drones, and WiFi CSI sensing —
              coordinated from a live disaster-zone Command Center.
            </p>
            <div className="flex flex-wrap items-center gap-3">
              <Button asChild size="lg">
                <a href={commandHref}>
                  Try simulation
                  <ArrowRight aria-hidden />
                </a>
              </Button>
              <Button variant="outline" size="lg" type="button" onClick={explore}>
                Explore fleet
              </Button>
            </div>
            <dl className="mt-10 grid max-w-md grid-cols-3 gap-4 border-t border-border/80 pt-6">
              {[
                ["4", "Spiderbots"],
                ["2", "Drones"],
                ["CSI", "Sensing"],
              ].map(([value, label]) => (
                <div key={label}>
                  <dt className="font-mono text-[10px] uppercase tracking-widest text-muted">
                    {label}
                  </dt>
                  <dd className="mt-1 text-2xl font-semibold text-foreground">
                    {value}
                  </dd>
                </div>
              ))}
            </dl>
          </div>

          <div className="relative min-h-[clamp(380px,52vh,720px)] lg:min-h-0">
            <div
              ref={interaction}
              id="planet"
              role="group"
              aria-roledescription="interactive 3D disaster zone"
              aria-label="Rotate the mission globe"
              aria-describedby="planet-instructions"
              tabIndex={0}
              className={cn(
                "absolute inset-0 touch-none select-none outline-none",
                auto ? "cursor-grab" : "cursor-default",
                dragging && "cursor-grabbing",
              )}
              onPointerDown={(event) => {
                if (!auto || !event.isPrimary || event.button !== 0) return;
                event.currentTarget.setPointerCapture(event.pointerId);
                drag.current = {
                  id: event.pointerId,
                  x: event.clientX,
                  y: event.clientY,
                };
                const m = motion.current;
                m.dragTarget = m.planetAngle;
                m.pitchTarget = m.pitchAngle;
                m.dragging = true;
                m.lastInteraction = m.time;
                setDragging(true);
              }}
              onPointerMove={(event) => {
                if (!auto || drag.current?.id !== event.pointerId) return;
                const dx = event.clientX - drag.current.x;
                const dy = event.clientY - drag.current.y;
                const sensitivity =
                  5 / Math.max(360, event.currentTarget.clientWidth);
                const m = motion.current;
                m.dragTarget = Math.max(
                  m.planetAngle - 0.5,
                  Math.min(m.planetAngle + 0.5, m.dragTarget + dx * sensitivity),
                );
                m.pitchTarget = Math.max(
                  m.pitchAngle - 0.4,
                  Math.min(
                    m.pitchAngle + 0.4,
                    m.pitchTarget + dy * sensitivity * 0.7,
                  ),
                );
                drag.current.x = event.clientX;
                drag.current.y = event.clientY;
                m.lastInteraction = m.time;
              }}
              onPointerUp={(event) => release(event.pointerId)}
              onPointerCancel={(event) => release(event.pointerId)}
              onLostPointerCapture={(event) => release(event.pointerId)}
              onKeyDown={(event) => {
                if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
                  event.preventDefault();
                  nudge(event.key === "ArrowRight" ? 1 : -1);
                }
                if (
                  auto &&
                  (event.key === "ArrowUp" || event.key === "ArrowDown")
                ) {
                  event.preventDefault();
                  motion.current.pitchVelocity +=
                    event.key === "ArrowDown" ? 0.4 : -0.4;
                  motion.current.lastInteraction = motion.current.time;
                }
                if (event.key === " ") {
                  event.preventDefault();
                  if (!event.repeat) toggleMotion();
                }
              }}
            >
              {sceneMounted && (
                <SceneBoundary>
                  <Suspense fallback={null}>
                    <SarPlanetScene
                      motion={motion}
                      active={visible && tabVisible && !story}
                      auto={auto}
                      reduced={reduced}
                      onReady={setReady}
                    />
                  </Suspense>
                </SceneBoundary>
              )}
              {!ready && (
                <div
                  className="pointer-events-none absolute inset-0 flex items-center justify-center gap-3 text-sm text-muted"
                  role="status"
                >
                  <span className="size-4 animate-spin rounded-full border border-border border-t-accent" />
                  Loading rescue scene…
                </div>
              )}
            </div>

            <div
              className={cn(
                "pointer-events-none absolute right-[6%] top-[14%] z-10 max-w-[140px] text-right text-sm italic leading-snug text-muted transition-opacity",
                dragging && "opacity-60",
              )}
              aria-hidden
            >
              <p>
                {!auto
                  ? "Press Start to patrol"
                  : dragging
                    ? "Mapping the zone."
                    : "Drag to rotate"}
                <br />
                {!auto ? "the disaster area" : dragging ? "Units deployed." : "the globe"}
              </p>
            </div>
          </div>

          <p id="planet-instructions" className="sr-only">
            Drag or use arrow keys to rotate the 3D globe. Space pauses patrol
            motion. Press again to resume.
          </p>

          <div
            className="pointer-events-none absolute inset-x-0 bottom-0 z-[1] h-48 bg-[radial-gradient(ellipse_at_center,rgba(249,115,22,0.08),transparent_68%)]"
            aria-hidden
          />
        </section>
      </main>

      <footer className="absolute bottom-6 left-[5%] right-[5%] z-20 flex items-end justify-between md:left-[6.5%] md:right-[6.5%]">
        <p className="max-w-[120px] font-mono text-[9px] uppercase leading-relaxed tracking-[0.22em] text-muted">
          WiFi CSI
          <br />
          Survivor lock
        </p>
        <button
          type="button"
          className="flex items-center gap-2 rounded-full px-3 py-2 text-[10px] uppercase tracking-widest text-muted transition hover:text-foreground"
          onClick={toggleMotion}
          aria-pressed={!auto}
          aria-label={auto ? "Pause patrol motion" : "Resume patrol motion"}
        >
          {auto ? <Pause className="size-4" /> : <Play className="size-4" />}
          <span className="hidden sm:inline">{auto ? "Pause" : "Start"}</span>
        </button>
        <p className="flex max-w-[120px] items-start justify-end gap-1 text-right font-mono text-[9px] uppercase leading-relaxed tracking-[0.22em] text-muted">
          <Radio className="mt-0.5 size-3 shrink-0 text-accent" aria-hidden />
          Live
          <br />
          telemetry
        </p>
      </footer>

      {story && (
        <StoryDialog story={story} onClose={() => setStory(null)} commandHref={commandHref} />
      )}
    </div>
  );
}

function StoryDialog({
  story,
  onClose,
  commandHref,
}: {
  story: string;
  onClose: () => void;
  commandHref: string;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const content = stories[story];

  useEffect(() => {
    const node = dialog.current;
    if (!node) return;
    if (!node.open) node.showModal();
    return () => node.close();
  }, []);

  return (
    <dialog
      ref={dialog}
      className="fixed top-1/2 left-1/2 z-50 w-[min(520px,calc(100%-2rem))] -translate-x-1/2 -translate-y-1/2 rounded-2xl border border-border bg-card p-8 text-foreground shadow-2xl backdrop:bg-black/60 open:flex open:flex-col"
      onCancel={onClose}
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <button
        type="button"
        className="absolute right-4 top-3 text-2xl text-muted hover:text-foreground"
        aria-label="Close"
        onClick={onClose}
      >
        ×
      </button>
      <span className="font-mono text-[11px] uppercase tracking-[0.28em] text-accent">
        {story}
      </span>
      <h2 className="mt-4 text-3xl font-semibold tracking-tight">
        {content.title}
      </h2>
      {content.paragraphs.map((paragraph) => (
        <p key={paragraph} className="mt-4 text-sm leading-relaxed text-muted">
          {paragraph}
        </p>
      ))}
      <Button asChild className="mt-6 self-start">
        <a href={commandHref}>
          Open Command Center
          <ArrowRight aria-hidden />
        </a>
      </Button>
    </dialog>
  );
}
