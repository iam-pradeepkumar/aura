import { useEffect, useState } from "react";
import type { NodeState, SensingState } from "../types/sensing";

const DEFAULT_NODES: NodeState[] = [
  { id: "ESP32-01", position: [-3.8, 0, -2.8], online: true, signalStrength: 0.88 },
  { id: "ESP32-02", position: [3.8, 0, -2.8], online: true, signalStrength: 0.91 },
  { id: "ESP32-03", position: [-3.8, 0, 2.8], online: true, signalStrength: 0.86 },
  { id: "ESP32-04", position: [3.8, 0, 2.8], online: true, signalStrength: 0.89 },
];

const BASE_STATE: SensingState = {
  nodes: DEFAULT_NODES,
  disturbance: {
    x: 0,
    z: 0,
    strength: 0.78,
    humanProbability: 0.87,
  },
  csi: {
    frequency: "5.18 GHz",
    phaseShift: 2.41,
    doppler: 0.31,
  },
};

function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t;
}

function smoothOsc(t: number, period: number, amplitude: number, offset = 0): number {
  return offset + Math.sin((t / period) * Math.PI * 2) * amplitude;
}

export function useSensingSimulation() {
  const [sensingState, setSensingState] = useState<SensingState>(BASE_STATE);
  const [selectedNode, setSelectedNode] = useState<string | null>(null);

  useEffect(() => {
    let raf = 0;
    const start = performance.now();

    const tick = () => {
      const elapsed = (performance.now() - start) / 1000;

      const breath = smoothOsc(elapsed, 5.2, 0.06);
      const driftX = smoothOsc(elapsed, 18, 0.35) + smoothOsc(elapsed, 7.3, 0.12);
      const driftZ = smoothOsc(elapsed, 22, 0.28) + smoothOsc(elapsed, 9.1, 0.1);

      const strength = lerp(0.72, 0.84, 0.5 + breath * 4);
      const humanProb = lerp(0.82, 0.91, 0.5 + smoothOsc(elapsed, 6.8, 0.5) * 0.5);

      setSensingState({
        nodes: BASE_NODES.map((node, i) => ({
          ...node,
          signalStrength: lerp(
            node.signalStrength,
            0.84 + smoothOsc(elapsed + i * 0.7, 11 + i, 0.05),
            0.08,
          ),
        })),
        disturbance: {
          x: driftX,
          z: driftZ,
          strength,
          humanProbability: humanProb,
        },
        csi: {
          frequency: "5.18 GHz",
          phaseShift: lerp(2.28, 2.54, 0.5 + smoothOsc(elapsed, 8.4, 0.5) * 0.5),
          doppler: lerp(0.24, 0.38, 0.5 + smoothOsc(elapsed, 4.6, 0.5) * 0.5),
        },
      });

      raf = requestAnimationFrame(tick);
    };

    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, []);

  return {
    sensingState,
    selectedNode,
    setSelectedNode,
  };
}
