import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";

const LINKS = [
  { id: "hero", label: "Home" },
  { id: "problem", label: "Problem" },
  { id: "solution", label: "Solution" },
  { id: "feasibility", label: "Feasibility" },
  { id: "demo", label: "Demo" },
];

export function PillNav({ commandHref = "/command" }: { commandHref?: string }) {
  const [active, setActive] = useState("hero");

  useEffect(() => {
    const ids = LINKS.map((l) => l.id);
    const nodes = ids
      .map((id) => document.getElementById(id))
      .filter(Boolean) as HTMLElement[];

    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
        if (visible?.target.id) setActive(visible.target.id);
      },
      { rootMargin: "-40% 0px -45% 0px", threshold: [0, 0.25, 0.5] },
    );

    nodes.forEach((node) => observer.observe(node));
    return () => observer.disconnect();
  }, []);

  return (
    <header className="fixed inset-x-0 top-0 z-50 flex justify-center px-4 pt-5">
      <nav
        className="flex max-w-full items-center gap-1 rounded-full border border-border/80 bg-background/70 px-2 py-2 shadow-[0_8px_32px_rgba(0,0,0,0.45)] backdrop-blur-xl"
        aria-label="Main navigation"
      >
        {LINKS.map(({ id, label }) => (
          <a
            key={id}
            href={`#${id}`}
            className={cn(
              "rounded-full px-3 py-1.5 text-xs font-medium transition-all duration-300 sm:px-4 sm:text-sm",
              active === id
                ? "bg-foreground text-background shadow-sm"
                : "text-muted hover:text-foreground",
            )}
          >
            {label}
          </a>
        ))}
        <a
          href={commandHref}
          className="ml-1 hidden rounded-full bg-accent px-4 py-1.5 text-xs font-semibold text-[#031018] transition hover:brightness-110 sm:inline-block sm:text-sm"
        >
          Simulate
        </a>
      </nav>
    </header>
  );
}
