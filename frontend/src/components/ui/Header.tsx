export function Header() {
  return (
    <header
      style={{
        position: "absolute",
        top: 0,
        left: 0,
        right: 0,
        height: 44,
        display: "grid",
        gridTemplateColumns: "1fr auto 1fr",
        alignItems: "center",
        padding: "0 20px",
        background: "var(--header-bg)",
        borderBottom: "1px solid var(--border)",
        backdropFilter: "blur(6px)",
        pointerEvents: "none",
      }}
    >
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
          letterSpacing: "0.16em",
          color: "var(--muted)",
          textTransform: "uppercase",
          textAlign: "center",
        }}
      >
        Wi-Fi Sensing Observatory
      </span>

      <div
        style={{
          justifySelf: "end",
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
            boxShadow: "0 0 5px rgba(70, 245, 196, 0.45)",
          }}
        />
        MESH LIVE
      </div>
    </header>
  );
}
