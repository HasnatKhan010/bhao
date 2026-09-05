"""Generate light + dark SVG banner and architecture diagram for the README."""

from pathlib import Path

THEMES = {
    "light": dict(
        bg0="#f0fdf4", bg1="#ffffff", ink="#052e16", sub="#475569",
        accent="#059669", accent2="#0d9488", band="#a7f3d0", bandline="#059669",
        box="#ffffff", boxline="#cbd5e1", store="#ecfdf5", storeline="#6ee7b7",
        chip="#f1f5f9", grid="#e2e8f0",
    ),
    "dark": dict(
        bg0="#020617", bg1="#0f172a", ink="#f1f5f9", sub="#94a3b8",
        accent="#34d399", accent2="#2dd4bf", band="#064e3b", bandline="#34d399",
        box="#1e293b", boxline="#334155", store="#052e16", storeline="#065f46",
        chip="#1e293b", grid="#1e293b",
    ),
}


def banner(t):
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="300" viewBox="0 0 1200 300" role="img" aria-label="Bhao banner">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="{t['bg0']}"/><stop offset="1" stop-color="{t['bg1']}"/>
    </linearGradient>
    <linearGradient id="band" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="{t['accent']}" stop-opacity=".28"/>
      <stop offset="1" stop-color="{t['accent']}" stop-opacity=".05"/>
    </linearGradient>
  </defs>
  <rect width="1200" height="300" fill="url(#bg)"/>
  <g font-family="system-ui,'Segoe UI',Roboto,sans-serif">
    <text x="72" y="128" font-size="84" font-weight="800" fill="{t['ink']}">&#1576;&#1726;&#1575;&#1569;</text>
    <text x="300" y="118" font-size="64" font-weight="800" fill="{t['accent']}">Bhao</text>
    <text x="74" y="176" font-size="21" fill="{t['sub']}">What things cost in Pakistan, weekly &#8212; and what they&#8217;ll cost next week.</text>
    <g font-size="14.5">
      <rect x="74"  y="204" width="182" height="34" rx="17" fill="{t['chip']}"/>
      <text x="90"  y="226" fill="{t['ink']}" font-weight="600">17 cities &#183; 51 items</text>
      <rect x="268" y="204" width="176" height="34" rx="17" fill="{t['chip']}"/>
      <text x="284" y="226" fill="{t['ink']}" font-weight="600">867 series, weekly</text>
      <rect x="456" y="204" width="216" height="34" rx="17" fill="{t['chip']}"/>
      <text x="472" y="226" fill="{t['ink']}" font-weight="600">h=1 forecast + p10/p90</text>
      <rect x="684" y="204" width="222" height="34" rx="17" fill="{t['chip']}"/>
      <text x="700" y="226" fill="{t['ink']}" font-weight="600">every error published</text>
      <rect x="918" y="204" width="208" height="34" rx="17" fill="{t['chip']}"/>
      <text x="934" y="226" fill="{t['ink']}" font-weight="600">&#1575;&#1585;&#1583;&#1608; / English &#183; RTL</text>
    </g>
  </g>
  <g transform="translate(760,40)">
    <rect x="0" y="0" width="360" height="150" rx="14" fill="{t['box']}" stroke="{t['boxline']}"/>
    <g stroke="{t['grid']}" stroke-width="1">
      <line x1="18" y1="35" x2="342" y2="35"/><line x1="18" y1="75" x2="342" y2="75"/>
      <line x1="18" y1="115" x2="342" y2="115"/>
    </g>
    <path d="M18,108 L48,100 L78,104 L108,88 L138,96 L168,72 L198,84 L228,66 L258,74 L288,52" fill="none" stroke="{t['accent2']}" stroke-width="3" stroke-linecap="round"/>
    <path d="M288,52 L342,34 L342,86 L288,66 Z" fill="url(#band)"/>
    <path d="M288,52 L342,34" stroke="{t['bandline']}" stroke-width="2.5" stroke-dasharray="6 5" fill="none"/>
    <path d="M288,66 L342,86" stroke="{t['bandline']}" stroke-width="2.5" stroke-dasharray="6 5" fill="none"/>
    <line x1="288" y1="59" x2="342" y2="59" stroke="{t['bandline']}" stroke-width="3"/>
    <circle cx="288" cy="59" r="4.5" fill="{t['accent']}"/>
    <g font-size="12" fill="{t['sub']}">
      <text x="22" y="142">observed</text>
      <text x="282" y="142" fill="{t['accent']}" font-weight="600">forecast p10&#8211;p90</text>
    </g>
  </g>
</svg>'''


def arch(t):
    def box(x, y, w, h, title, lines, accent):
        items = "".join(
            f'<text x="{x + 16}" y="{y + 50 + i * 22}" font-size="13.5" fill="{t["sub"]}">{ln}</text>'
            for i, ln in enumerate(lines)
        )
        return (
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="{t["box"]}" stroke="{t["boxline"]}"/>'
            f'<rect x="{x}" y="{y}" width="4" height="{h}" rx="2" fill="{accent}"/>'
            f'<text x="{x + 16}" y="{y + 28}" font-size="15.5" font-weight="700" fill="{t["ink"]}">{title}</text>'
            + items
        )

    def store(x, y, w, h, name, lines):
        items = "".join(
            f'<text x="{x + 16}" y="{y + 54 + i * 22}" font-size="13" fill="{t["sub"]}">{ln}</text>'
            for i, ln in enumerate(lines)
        )
        return (
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="{t["store"]}" '
            f'stroke="{t["storeline"]}" stroke-dasharray="5 4"/>'
            f'<text x="{x + 16}" y="{y + 28}" font-size="14.5" font-weight="700" fill="{t["accent"]}">{name}</text>'
            + items
        )

    def arrow(x1, y1, x2, y2):
        return (f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{t["sub"]}" '
                f'stroke-width="1.6" marker-end="url(#arr2)"/>')

    A = t["accent"]
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="470" viewBox="0 0 1200 470" role="img" aria-label="Bhao architecture">
  <defs>
    <marker id="arr2" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M0,0 L10,5 L0,10 z" fill="{t['sub']}"/>
    </marker>
  </defs>
  <rect width="1200" height="470" fill="{t['bg1']}"/>
  <g font-family="system-ui,'Segoe UI',Roboto,sans-serif">
    <g font-size="13" font-weight="700" fill="{t['sub']}">
      <text x="120" y="42" letter-spacing="2">TRACK A &#183; INGEST</text>
      <text x="470" y="42" letter-spacing="2">TRACK B &#183; MODEL</text>
      <text x="840" y="42" letter-spacing="2">TRACK C &#183; SERVE</text>
    </g>
    {box(30, 60, 210, 150, "Sources", ["PBS weekly SPI (xlsx)", "Wayback CDX backfill", "WFP/HDX monthly"], "#f59e0b")}
    {box(30, 240, 210, 130, "Ingest pipeline", ["discover &#183; fetch", "parse (regex blocks)", "validate (Pandera)", "publish (revisions)"], A)}
    {store(280, 150, 170, 120, "data/panel", ["prices_weekly", "items &#183; cities", "national_weekly"])}
    {box(490, 60, 210, 110, "Features", ["lags &#183; rolls &#183; spread", "Hijri / Ramadan flags", "lagged cross-sectional"], A)}
    {box(490, 200, 210, 110, "Models", ["6 statistical baselines", "pooled quantile GBM", "per-series ensemble"], A)}
    {box(490, 340, 210, 100, "Evaluation", ["rolling-origin folds", "as_of() every fold", "MASE + coverage"], A)}
    {store(740, 150, 170, 120, "data/forecasts", ["forecasts", "metrics", "drift"])}
    {box(950, 60, 220, 110, "API", ["FastAPI + DuckDB", "read-only, no ML", "OpenAPI contract"], A)}
    {box(950, 200, 220, 110, "Web app", ["Next.js bilingual", "Urdu RTL &#183; Nastaliq", "charts with honest gaps"], A)}
    {box(950, 340, 220, 100, "Ops", ["GH Actions weekly cron", "docker compose", "healthcheck on freshness"], A)}
    {arrow(240, 135, 278, 185)}
    {arrow(240, 305, 278, 225)}
    {arrow(450, 200, 488, 115)}
    {arrow(450, 200, 488, 255)}
    {arrow(700, 115, 738, 185)}
    {arrow(700, 255, 738, 215)}
    {arrow(700, 390, 948, 390)}
    {arrow(910, 210, 948, 125)}
    {arrow(910, 210, 948, 255)}
    <rect x="30" y="418" width="1140" height="34" rx="8" fill="none" stroke="{t['boxline']}"/>
    <text x="46" y="440" font-size="13.5" fill="{t['sub']}">The API never imports training code &#8212; it reads parquet via DuckDB only. A broken training run cannot take the site down. Every price row carries its source URL.</text>
  </g>
</svg>'''


out = Path("docs/assets")
out.mkdir(parents=True, exist_ok=True)
for name, fn in (("banner", banner), ("architecture", arch)):
    (out / f"{name}-light.svg").write_text(fn(THEMES["light"]), encoding="utf-8")
    (out / f"{name}-dark.svg").write_text(fn(THEMES["dark"]), encoding="utf-8")
print("SVGs written:", sorted(p.name for p in out.iterdir()))
