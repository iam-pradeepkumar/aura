"use client";

import { ArrowRight, Radar, Radio } from "lucide-react";
import { useState } from "react";
import { SketchfabFleet } from "@/components/landing/SketchfabFleet";
import { Button } from "@/components/ui/button";

const stories: Record<string, { title: string; paragraphs: string[] }> = {
  Problem: {
    title: "The golden hour is lost in rubble.",
    paragraphs: [
      "After earthquakes and building collapses, survivors are buried where GPS fails, cameras cannot see, and human teams cannot safely enter.",
      "Urban search and rescue needs autonomous eyes underground and in the air before the window for rescue closes.",
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
      "The dashboard runs a full mission loop with geo-anchored units, survivor pins, and fleet telemetry ready to swap simulated feeds for Isaac Sim and live hardware.",
      "Render-hosted deployment means every push to main updates the public demo your team can share with judges and partners.",
    ],
  },
};

type OrbitDeliveryHeroProps = {
  theme?: "auto" | "light" | "dark";
  commandHref?: string;
};

export default function OrbitDeliveryHero({
  theme = "dark",
  commandHref = "/command",
}: OrbitDeliveryHeroProps) {
  const [story, setStory] = useState<string | null>(null);

  const explore = () => {
    document.getElementById("fleet")?.scrollIntoView({
      behavior: "smooth",
      block: "center",
    });
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
            Fleet
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
          className="relative grid min-h-[calc(100svh-88px)] grid-cols-1 lg:grid-cols-[minmax(0,44%)_1fr]"
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
              Autonomous spiderbots, quadrotor drones, and WiFi CSI sensing
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
                View 3D fleet
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

          <div className="relative min-h-[clamp(420px,55vh,760px)] lg:min-h-0">
            <SketchfabFleet />
            <p className="pointer-events-none absolute bottom-4 left-1/2 z-10 -translate-x-1/2 text-center text-xs text-muted">
              Drag to rotate each model · scroll to zoom
            </p>
          </div>

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
        <p className="flex max-w-[140px] items-start justify-end gap-1 text-right font-mono text-[9px] uppercase leading-relaxed tracking-[0.22em] text-muted">
          <Radio className="mt-0.5 size-3 shrink-0 text-accent" aria-hidden />
          Sketchfab
          <br />
          fleet models
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
  const content = stories[story];

  return (
    <dialog
      open
      className="fixed top-1/2 left-1/2 z-50 w-[min(520px,calc(100%-2rem))] -translate-x-1/2 -translate-y-1/2 rounded-2xl border border-border bg-card p-8 text-foreground shadow-2xl backdrop:bg-black/60 open:flex open:flex-col"
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
