# AURA Landing (React + shadcn + Tailwind)

Modern landing page built with **Vite**, **TypeScript**, **Tailwind CSS v4**, and **shadcn/ui** conventions.

## Structure

| Path | Purpose |
|------|---------|
| `src/components/ui/orbit-delivery-hero.tsx` | Hero layout + story dialogs |
| `src/components/landing/SketchfabFleet.tsx` | Sketchfab spiderbot + drone embeds |
| `src/components/ui/button.tsx` | shadcn `Button` primitive |
| `src/lib/utils.ts` | `cn()` helper for Tailwind class merging |
| `components.json` | shadcn CLI config (`ui` → `@/components/ui`) |

## Setup (local)

```bash
cd landing
npm install
npm run dev      # http://127.0.0.1:4317
npm run build    # → ../dashboard/static/landing-dist/
```

## shadcn CLI (optional)

If you add more primitives:

```bash
npx shadcn@latest init   # already configured via components.json
npx shadcn@latest add card dialog
```

Components live under `src/components/ui/` — this matches shadcn defaults and keeps UI primitives separate from page logic.

## FastAPI integration

`dashboard/app.py` serves `landing-dist/index.html` at `/` when the build exists. Render runs `npm run build` during deploy (see root `render.yaml`).
