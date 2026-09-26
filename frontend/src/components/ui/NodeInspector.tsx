import type { NodeState } from "../../types/sensing";

interface NodeInspectorProps {
  node: NodeState;
  onClose: () => void;
}

export function NodeInspector({ node, onClose }: NodeInspectorProps) {
  const signalPct = Math.round(node.signalStrength * 100);

  return (
    <div
      style={{
        position: "absolute",
        bottom: 18,
        left: 18,
        minWidth: 140,
        padding: "12px 14px",
        background: "var(--panel-bg)",
        border: "1px solid var(--border)",
        backdropFilter: "blur(8px)",
        fontFamily: "var(--font-mono)",
        fontSize: 9,
        letterSpacing: "0.08em",
        lineHeight: 1.7,
      }}
    >
      <button
        type="button"
        onClick={onClose}
        aria-label="Close inspector"
        style={{
          position: "absolute",
          top: 6,
          right: 8,
          fontSize: 12,
          color: "var(--muted)",
          padding: 2,
          pointerEvents: "auto",
        }}
      >
        ×
      </button>
      <div style={{ color: "var(--text)", fontSize: 10, marginBottom: 6 }}>{node.id}</div>
      <div style={{ color: node.online ? "var(--healthy)" : "var(--critical)", marginBottom: 10 }}>
        {node.online ? "ONLINE" : "OFFLINE"}
      </div>
      <div style={{ color: "var(--muted)" }}>SIGNAL</div>
      <div style={{ color: "var(--rf-cyan)", marginBottom: 8 }}>{signalPct}%</div>
      <div style={{ color: "var(--muted)" }}>CSI</div>
      <div style={{ color: "var(--text)" }}>ACTIVE</div>
    </div>
  );
}
