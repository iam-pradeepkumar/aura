import { ArrowRight, Cpu, Map, Shield } from "lucide-react";
import OrbitDeliveryHero from "@/components/ui/orbit-delivery-hero";
import { Button } from "@/components/ui/button";

const pillars = [
  {
    icon: Map,
    title: "Disaster zone mapping",
    body:
      "MapLibre 3D terrain with pitch-aligned unit markers keeps spiderbots, drones, and survivor pins locked to real coordinates during mission tilt and rotation.",
  },
  {
    icon: Cpu,
    title: "WiFi CSI detection",
    body:
      "Channel State Information picks up micro-movements through rubble — triggering autonomous search patterns before visual contact.",
  },
  {
    icon: Shield,
    title: "Simulation to hardware",
    body:
      "The same mission loop powers the public demo today and is structured to plug into NVIDIA Isaac Sim and live fleet hardware next.",
  },
];

export default function App() {
  return (
    <div className="bg-background text-foreground">
      <OrbitDeliveryHero commandHref="/command" theme="dark" />

      <section
        id="how-it-works"
        className="border-t border-border bg-[#070b14] px-[5%] py-20 md:px-[6.5%]"
      >
        <div className="mx-auto max-w-6xl">
          <p className="font-mono text-[11px] uppercase tracking-[0.28em] text-accent">
            How AURA works
          </p>
          <h2 className="mt-3 max-w-2xl text-3xl font-semibold tracking-tight md:text-4xl">
            Problem, sensing layer, and autonomous response — in one stack.
          </h2>
          <div className="mt-12 grid gap-6 md:grid-cols-3">
            {pillars.map(({ icon: Icon, title, body }) => (
              <article
                key={title}
                className="rounded-2xl border border-border bg-card/60 p-6 backdrop-blur-sm"
              >
                <Icon className="mb-4 size-6 text-accent" aria-hidden />
                <h3 className="text-lg font-semibold">{title}</h3>
                <p className="mt-3 text-sm leading-relaxed text-muted">{body}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="border-t border-border px-[5%] py-20 md:px-[6.5%]">
        <div className="mx-auto grid max-w-6xl gap-10 lg:grid-cols-2 lg:items-center">
          <div>
            <p className="font-mono text-[11px] uppercase tracking-[0.28em] text-accent">
              Project demo
            </p>
            <h2 className="mt-3 text-3xl font-semibold tracking-tight md:text-4xl">
              See the fleet coordination in action.
            </h2>
            <p className="mt-4 text-muted leading-relaxed">
              Watch how AURA combines ground crawlers, aerial scouts, and CSI
              survivor detection inside a collapsed urban environment.
            </p>
            <Button asChild className="mt-8" size="lg">
              <a href="/command">
                Run live simulation
                <ArrowRight aria-hidden />
              </a>
            </Button>
          </div>
          <div className="overflow-hidden rounded-2xl border border-border bg-black shadow-2xl">
            <iframe
              className="aspect-video w-full"
              src="https://www.youtube.com/embed/Tj6D4ykAHcQ"
              title="AURA Search and Rescue demo"
              allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
              allowFullScreen
            />
          </div>
        </div>
      </section>

      <section className="border-t border-border bg-[radial-gradient(ellipse_at_center,rgba(249,115,22,0.12),transparent_65%)] px-[5%] py-20 md:px-[6.5%]">
        <div className="mx-auto flex max-w-4xl flex-col items-center text-center">
          <h2 className="text-3xl font-semibold tracking-tight md:text-4xl">
            Ready to launch a mission?
          </h2>
          <p className="mt-4 max-w-xl text-muted">
            Mark the disaster zone, deploy the fleet, and watch autonomous units
            search until survivors are confirmed on the tactical map.
          </p>
          <Button asChild size="lg" className="mt-8">
            <a href="/command">
              Launch Command Center
              <ArrowRight aria-hidden />
            </a>
          </Button>
        </div>
      </section>

      <footer className="border-t border-border px-[5%] py-8 text-center text-xs text-muted md:px-[6.5%]">
        AURA — Autonomous Urban Rescue Architecture · Simulation dashboard on Render
      </footer>
    </div>
  );
}
