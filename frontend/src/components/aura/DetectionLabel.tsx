import { Html } from "@react-three/drei";
import type { DisturbanceState } from "../../types/sensing";

interface DetectionLabelProps {
  disturbance: DisturbanceState;
}

export function DetectionLabel({ disturbance }: DetectionLabelProps) {
  const conf = Math.round(disturbance.humanProbability * 100);

  return (
    <Html
      position={[disturbance.x + 1.15, 0.55, disturbance.z + 0.35]}
      center={false}
      distanceFactor={8}
      style={{ pointerEvents: "none" }}
    >
      <div
        style={{
          fontFamily: "var(--font-mono)",
          fontSize: "10px",
          letterSpacing: "0.08em",
          lineHeight: 1.5,
          whiteSpace: "nowrap",
        }}
      >
        <div style={{ color: "#FFB000", fontWeight: 500, marginBottom: 2 }}>
          POSSIBLE HUMAN
        </div>
        <div style={{ color: "#C9FAFF", marginBottom: 2 }}>{conf}% CONF</div>
        <div style={{ color: "#4A9CA9" }}>ZONE B-03</div>
      </div>
    </Html>
  );
}
