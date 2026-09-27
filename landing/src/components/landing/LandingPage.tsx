import { ArrowRight } from "lucide-react";
import { PillNav } from "@/components/landing/PillNav";
import { Reveal } from "@/components/landing/Reveal";
import { SketchfabFleet } from "@/components/landing/SketchfabFleet";
import { Button } from "@/components/ui/button";

type LandingPageProps = {
  commandHref?: string;
};

export default function LandingPage({ commandHref = "/command" }: LandingPageProps) {
  return (
    <div className="relative min-h-[100svh] bg-background text-foreground">
      <div
        className="pointer-events-none fixed inset-0 z-0 bg-[radial-gradient(ellipse_80%_50%_at_50%_-10%,rgba(14,165,233,0.12),transparent_55%)]"
        aria-hidden
      />
      <PillNav commandHref={commandHref} />

      {/* Hero */}
      <section
        id="hero"
        className="relative z-10 mx-auto grid min-h-[100svh] max-w-6xl scroll-mt-24 grid-cols-1 items-center gap-10 px-[5%] pb-16 pt-28 md:px-8 lg:grid-cols-[minmax(0,42%)_1fr] lg:gap-14 lg:pb-20 lg:pt-32"
      >
        <Reveal>
          <p className="mb-4 font-mono text-[11px] uppercase tracking-[0.32em] text-accent">
            Autonomous SAR
          </p>
          <h1 className="max-w-xl text-[clamp(2.5rem,5.5vw,4.25rem)] font-semibold leading-[1.04] tracking-[-0.04em]">
            Find survivors
            <br />
            <span className="text-accent">before time</span>
            <br />
            runs out.
          </h1>
          <p className="mt-5 max-w-md text-base leading-relaxed text-muted md:text-lg">
            Spiderbots, drones, and WiFi CSI sensing coordinated from one live
            disaster-zone command map.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Button asChild size="lg">
              <a href={commandHref}>
                Try simulation
                <ArrowRight aria-hidden />
              </a>
            </Button>
            <Button asChild variant="outline" size="lg">
              <a href="#problem">Read the story</a>
            </Button>
          </div>
        </Reveal>

        <Reveal delay={120} className="relative">
          <SketchfabFleet id="fleet" />
          <p className="mt-3 text-center text-xs text-muted">
            Drag to rotate · scroll to zoom each model
          </p>
        </Reveal>
      </section>

      {/* Problem */}
      <section
        id="problem"
        className="relative z-10 scroll-mt-24 border-t border-border/80 bg-[#07090e]/80 py-20 md:py-28"
      >
        <div className="mx-auto max-w-6xl px-[5%] md:px-8">
          <Reveal>
            <h2 className="max-w-2xl text-3xl font-semibold tracking-tight md:text-[2.75rem] md:leading-[1.08]">
              When rubble blocks every sensor you trust
            </h2>
            <p className="mt-4 max-w-2xl text-muted leading-relaxed">
              After earthquakes and collapses, survivors are buried where GPS fails,
              optics cannot see, and human teams cannot safely enter at scale.
            </p>
          </Reveal>

          <div className="mt-12 grid gap-4 md:grid-cols-12">
            <Reveal delay={80} className="md:col-span-7">
              <article className="h-full rounded-2xl border border-border bg-card/50 p-8 backdrop-blur-sm">
                <h3 className="text-xl font-semibold">Visibility fails underground</h3>
                <p className="mt-4 text-sm leading-relaxed text-muted">
                  Thermal cameras and optics stop at the rubble line. Dogs and
                  microphones cannot systematically sweep a full city block before
                  the golden hour closes.
                </p>
              </article>
            </Reveal>
            <Reveal delay={140} className="md:col-span-5">
              <article className="h-full rounded-2xl border border-border bg-card/50 p-8 backdrop-blur-sm">
                <h3 className="text-xl font-semibold">Coverage is too slow</h3>
                <p className="mt-4 text-sm leading-relaxed text-muted">
                  Manual search cannot lawnmower a disaster polygon with the speed
                  autonomous fleets can maintain hour after hour.
                </p>
              </article>
            </Reveal>
            <Reveal delay={200} className="md:col-span-12">
              <article className="rounded-2xl border border-dashed border-border/90 bg-background/40 p-8">
                <h3 className="text-xl font-semibold">Alert and coordination gaps</h3>
                <p className="mt-4 max-w-3xl text-sm leading-relaxed text-muted">
                  Communities lack hyper-local early warning. After impact, agencies
                  fragment across tools that were never built for survivor localization
                  through debris.
                </p>
              </article>
            </Reveal>
          </div>
        </div>
      </section>

      {/* Solution */}
      <section
        id="solution"
        className="relative z-10 scroll-mt-24 border-t border-border/80 py-20 md:py-28"
      >
        <div className="mx-auto grid max-w-6xl gap-12 px-[5%] md:grid-cols-2 md:items-center md:px-8">
          <Reveal>
            <h2 className="text-3xl font-semibold tracking-tight md:text-[2.75rem] md:leading-[1.08]">
              WiFi CSI turns the air into a sensor
            </h2>
            <p className="mt-4 text-muted leading-relaxed">
              Channel State Information captures micro-movements through rubble.
              AURA fuses multinode signals to estimate count, position, respiration,
              and triage hints without line of sight.
            </p>
            <ol className="mt-8 space-y-4">
              {[
                ["Mark zone", "Draw a real disaster polygon on satellite imagery at any address."],
                ["Deploy fleet", "Spiderbots crawl; drones sweep. Both home on survivor WiFi signatures."],
                ["Confirm FOUND", "CSI vitals lock survivor coordinates on the live command map."],
              ].map(([title, body], i) => (
                <li
                  key={title}
                  className="flex gap-4 rounded-xl border border-border/70 bg-card/40 p-4"
                >
                  <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-accent/15 font-mono text-sm font-semibold text-accent">
                    {i + 1}
                  </span>
                  <div>
                    <p className="font-semibold">{title}</p>
                    <p className="mt-1 text-sm text-muted">{body}</p>
                  </div>
                </li>
              ))}
            </ol>
          </Reveal>

          <Reveal delay={100}>
            <div className="rounded-2xl border border-border bg-card/30 p-6 backdrop-blur-sm">
              <SketchfabFleet layout="stack" id="fleet-solution" />
            </div>
          </Reveal>
        </div>
      </section>

      {/* Feasibility */}
      <section
        id="feasibility"
        className="relative z-10 scroll-mt-24 border-t border-border/80 bg-[#07090e]/80 py-20 md:py-28"
      >
        <div className="mx-auto max-w-6xl px-[5%] md:px-8">
          <Reveal>
            <h2 className="text-3xl font-semibold tracking-tight md:text-[2.75rem]">
              Feasibility and viability
            </h2>
            <p className="mt-4 max-w-2xl text-muted leading-relaxed">
              Built for field deployment economics, offline rescue ops, and a clear
              path from browser simulation to Isaac Sim and live hardware.
            </p>
          </Reveal>

          <div className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {[
              ["$40", "ESP32 node BOM", "Commodity WiFi CSI hardware proven in research pilots."],
              ["Offline", "Hotspot mesh", "Rescue sensing runs without cloud when towers are down."],
              ["ROS 2", "Gazebo + Isaac", "Same mission YAML from dashboard to photoreal sim."],
              ["8x", "Sim scale", "Accelerated patrol so operators validate workflows fast."],
            ].map(([val, lbl, note], i) => (
              <Reveal key={lbl} delay={i * 60}>
                <article className="flex h-full flex-col rounded-2xl border border-border bg-card/50 p-6 transition hover:border-accent/30">
                  <span className="font-mono text-2xl font-semibold text-accent">{val}</span>
                  <span className="mt-1 font-mono text-[10px] uppercase tracking-[0.2em] text-muted">
                    {lbl}
                  </span>
                  <p className="mt-4 text-sm leading-relaxed text-muted">{note}</p>
                </article>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {/* Demo video */}
      <section
        id="demo"
        className="relative z-10 scroll-mt-24 border-t border-border/80 py-20 md:py-28"
      >
        <div className="mx-auto grid max-w-6xl gap-10 px-[5%] md:grid-cols-2 md:items-center md:px-8">
          <Reveal>
            <h2 className="text-3xl font-semibold tracking-tight md:text-4xl">
              See the field demo
            </h2>
            <p className="mt-4 text-muted leading-relaxed">
              How WiFi CSI sensing locates survivors and feeds the rescue command
              workflow in a collapsed urban environment.
            </p>
            <Button asChild className="mt-8" size="lg">
              <a href={commandHref}>
                Run live simulation
                <ArrowRight aria-hidden />
              </a>
            </Button>
          </Reveal>
          <Reveal delay={100}>
            <div className="overflow-hidden rounded-2xl border border-border bg-black shadow-2xl">
              <iframe
                className="aspect-video w-full"
                src="https://www.youtube.com/embed/Tj6D4ykAHcQ?rel=0&modestbranding=1"
                title="AURA Search and Rescue demo"
                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                allowFullScreen
              />
            </div>
          </Reveal>
        </div>
      </section>

      {/* CTA */}
      <section className="relative z-10 border-t border-border/80 py-20 md:py-24">
        <Reveal className="mx-auto flex max-w-4xl flex-col items-center px-[5%] text-center md:px-8">
          <h2 className="text-3xl font-semibold tracking-tight md:text-4xl">
            Ready to launch a mission?
          </h2>
          <p className="mt-4 max-w-lg text-muted">
            Mark the disaster zone, deploy the fleet, and watch autonomous units
            search until survivors are confirmed on the map.
          </p>
          <Button asChild size="lg" className="mt-8">
            <a href={commandHref}>
              Launch Command Center
              <ArrowRight aria-hidden />
            </a>
          </Button>
        </Reveal>
      </section>

      <footer className="relative z-10 border-t border-border/80 px-[5%] py-8 text-center text-xs text-muted md:px-8">
        AURA — Autonomous Urban Rescue Architecture
      </footer>
    </div>
  );
}
