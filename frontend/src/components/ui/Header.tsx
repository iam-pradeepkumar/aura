export function Header() {
  return (
    <header
      style={{
        position: "absolute",
        top: 0,
        left: 0,
        right: 0,
        height: 48,
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "0 20px",
        background: "var(--header-bg)",
        borderBottom: "1px solid var(--border)",
        backdropFilter: "blur(6px)",
        pointerEvents: "none",
      }}
    >
      <div style={{ display: "flex", alignItems: "baseline", gap: 14 }}>
        <span
          style={{
            fontSize: 13,
            fontWeight: 600,
            letterSpacing: "0.22em",
            color: "var(--text)",
          }}
        >
          AURA
        </span>
        <span
          style={{
            fontSize: 10,
            letterSpacing: "0.14em",
            color: "var(--muted)",
            textTransform: "uppercase",
          }}
        >
          Wi-Fi Sensing Observatory
        </span>
      </div>
      <div
        style={{
          fontFamily: "var(--font-mono)",
          fontSize: 9,
          letterSpacing: "0.1em",
          color: "var(--healthy)",
          display: "flex",
          alignItems: "center",
          gap: 6,
        }}
      >
        <span
          style={{
            width: 6,
            height: 6,
            borderRadius: "50%",
            background: "var(--healthy)",
            boxShadow: "0 0 6px rgba(70, 245, 196, 0.5)",
          }}
        />
        MESH LIVE
      </div>
    </header>
  );
}
