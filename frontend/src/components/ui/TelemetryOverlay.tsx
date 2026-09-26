import type { CSSProperties } from "react";
import type { SensingState } from "../../types/sensing";

interface TelemetryOverlayProps {
  sensingState: SensingState;
}

const mono: CSSProperties = {
  fontFamily: "var(--font-mono)",
  letterSpacing: "0.08em",
};

export function TelemetryOverlay({ sensingState }: TelemetryOverlayProps) {
  const online = sensingState.nodes.filter((n) => n.online).length;
  const { csi } = sensingState;

  return (
    <>
      <div
        style={{
          position: "absolute",
          top: 58,
          left: 18,
          ...mono,
          fontSize: 9,
          lineHeight: 1.65,
          color: "var(--muted)",
          pointerEvents: "none",
        }}
      >
        <div style={{ color: "var(--text)", fontSize: 10, marginBottom: 4 }}>
          AURA RF-CSI OBSERVATORY
        </div>
        <div>DEVICE-FREE SUB-CARRIER MULTIPATH INVERSION</div>
      </div>

      <div
        style={{
          position: "absolute",
          top: 58,
          right: 18,
          textAlign: "right",
          ...mono,
          fontSize: 9,
          lineHeight: 1.65,
          color: "var(--text)",
          pointerEvents: "none",
        }}
      >
        <div>{online} NODES ONLINE</div>
        <div style={{ color: "var(--muted)" }}>
          CSI ACTIVE · {csi.frequency}
        </div>
      </div>

      <div
        style={{
          position: "absolute",
          bottom: 18,
          right: 18,
          textAlign: "right",
          ...mono,
          fontSize: 9,
          lineHeight: 1.7,
          color: "var(--muted)",
          pointerEvents: "none",
        }}
      >
        <div style={{ color: "var(--rf-cyan-secondary)", marginBottom: 2 }}>ZONE B-03</div>
        <div>PHASE +{csi.phaseShift.toFixed(2)} rad</div>
        <div>DOPPLER {csi.doppler.toFixed(2)} Hz</div>
      </div>
    </>
  );
}
