# AURA Wi-Fi Sensing Observatory (Phase 1)

Standalone React + TypeScript + Vite + Three.js frontend. **Does not modify** the existing Python/FastAPI dashboard.

## Run locally

```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:4317**

## Stack

- React 18
- TypeScript
- Vite 5
- Three.js + @react-three/fiber + @react-three/drei

## Architecture

- `useSensingSimulation()` — local animated `SensingState` (no backend yet)
- `AuraScene` — full-viewport RF field visualization
- UI overlays — header, telemetry, node inspector

Backend adapter (FastAPI / WebSocket / ESP32) will be added in a later phase.
