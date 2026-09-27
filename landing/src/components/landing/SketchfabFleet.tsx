const EMBED_QUERY =
  "autostart=1&autospin=0.35&transparent=1&ui_theme=dark&ui_animations=0&ui_infos=0&ui_stop=0&ui_inspector=0&ui_watermark=0&ui_help=0&ui_settings=0&ui_vr=0&ui_fullscreen=0";

type SketchfabModelProps = {
  title: string;
  modelId: string;
  label: string;
  role: string;
};

function SketchfabModel({ title, modelId, label, role }: SketchfabModelProps) {
  const src = `https://sketchfab.com/models/${modelId}/embed?${EMBED_QUERY}`;

  return (
    <article className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-2xl border border-border/80 bg-[#0a1018]/80 shadow-[0_24px_80px_rgba(0,0,0,0.45)] backdrop-blur-sm">
      <div className="flex items-center justify-between border-b border-border/60 px-4 py-2.5">
        <div>
          <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-accent">
            {role}
          </p>
          <h3 className="text-sm font-semibold text-foreground">{label}</h3>
        </div>
        <span className="rounded-full border border-border px-2 py-0.5 font-mono text-[9px] uppercase tracking-widest text-muted">
          3D
        </span>
      </div>
      <div className="relative min-h-[220px] flex-1 bg-[radial-gradient(ellipse_at_50%_40%,rgba(14,165,233,0.1),transparent_70%)]">
        <iframe
          title={title}
          src={src}
          className="absolute inset-0 h-full w-full border-0"
          allow="autoplay; fullscreen; xr-spatial-tracking"
          allowFullScreen
          loading="lazy"
        />
      </div>
    </article>
  );
}

export function SketchfabFleet() {
  return (
    <div
      id="fleet"
      className="grid h-full min-h-[clamp(380px,52vh,720px)] grid-cols-1 gap-4 p-4 md:p-6 lg:min-h-0 lg:grid-cols-2"
      aria-label="AURA autonomous fleet 3D models"
    >
      <SketchfabModel
        title="Robot spider"
        modelId="c9c7188c7f9e4504b8499f1131693b72"
        label="Spiderbot"
        role="Ground unit"
      />
      <SketchfabModel
        title="Inside Drone"
        modelId="d38af0afb72343f69eed6da6457df11b"
        label="Quadrotor drone"
        role="Aerial unit"
      />
    </div>
  );
}
