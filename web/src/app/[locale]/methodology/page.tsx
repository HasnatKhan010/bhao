"use client";

import { useTranslations } from "next-intl";

export default function MethodologyPage() {
  const t = useTranslations();

  return (
    <div className="max-w-3xl space-y-8">
      <h1 className="text-2xl font-bold">{t("methodology.title")}</h1>
      <p className="text-slate-600">{t("methodology.intro")}</p>

      <section>
        <h2 className="text-lg font-semibold">{t("methodology.sources")}</h2>
        <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-700">
          <li><b>Pakistan Bureau of Statistics — Weekly Sensitive Price Indicator (SPI).</b> Published
            every Friday for the week ending Thursday: 17 cities × 51 commodities, min/avg/max, as
            merged-cell Excel with three header rows. Bhao scrapes and normalises this itself; every
            cell carries its source URL.</li>
          <li><b>WFP/HDX monthly food prices (2004–2026).</b> An existing open dataset used for
            long-history validation and seasonality context. <b>Not</b> scraped by Bhao, and never
            mixed into the weekly panel as if it were the same measurement.</li>
          <li><b>Wayback Machine CDX.</b> The ~14 live posts do not cover history; the archive's xlsx
            captures do. The coverage report publishes exactly which weeks were recovered and which
            are missing.</li>
        </ul>
      </section>

      <section>
        <h2 className="text-lg font-semibold">{t("methodology.parse")}</h2>
        <p className="mt-2 text-sm text-slate-700">
          The annex parser finds city blocks by regex on the “(NN)” suffix — never by hardcoded rows —
          so a layout change fails loudly instead of silently shifting every price one commodity down.
          A cross-check against the national table (unweighted mean of the 17 city averages vs PBS's
          weighted national figure, within 30%) catches column-offset bugs. “-” means not surveyed and
          stays null; numbers are coerced from strings like “1,171.55”.
        </p>
      </section>

      <section>
        <h2 className="text-lg font-semibold">{t("methodology.revisions")}</h2>
        <p className="mt-2 text-sm text-slate-700">
          PBS restates figures. Bhao appends a revision row instead of overwriting, and every backtest
          fold trains through an as-of filter that sees only what was knowable at forecast time. A
          restatement that arrived after the forecast is invisible to it.
        </p>
      </section>

      <section>
        <h2 className="text-lg font-semibold">{t("methodology.metrics")}</h2>
        <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-700">
          <li><b>MASE</b> = MAE(model) ÷ MAE(seasonal-naive, in-sample, on the fold's own training
            portion). MASE &lt; 1 means better than naive. Because Pakistani prices carry ~9% headline
            YoY inflation, the lag-52 denominator is inflated by drift itself, so a second column,
            MASE vs last week (lag-1), is reported alongside.</li>
          <li><b>coverage@80</b> — the fraction of actuals inside [p10, p90]. Should be ≈ 80%; a number
            that misses is published anyway.</li>
          <li><b>Rolling-origin backtest</b>, h=1 week, no random splits, no shuffle. K is set by the
            panel's real depth and reduced rather than faked.</li>
        </ul>
      </section>

      <section>
        <h2 className="text-lg font-semibold">{t("methodology.ethics")}</h2>
        <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-700">
          <li>robots.txt permits crawling; requests are rate-limited to 1 per 2 s; every artefact is
            cached so nothing is fetched twice.</li>
          <li>Bhao does not modify observed prices. Nulls are shown as nulls.</li>
          <li>Forecasts are model output, not advice, and the error record is published alongside
            them.</li>
        </ul>
      </section>

      <section>
        <h2 className="text-lg font-semibold">{t("methodology.limitations")}</h2>
        <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-700">
          <li>h=1 week only — nothing here supports a claim beyond one week.</li>
          <li>Coverage is what PBS surveyed: 17 cities, 51 retail commodities. Not a national average
            of all prices, not a CPI substitute.</li>
          <li>The panel starts where the archive starts; the coverage report publishes the missing
            weeks rather than interpolating them.</li>
          <li>No causal claims — correlates and lags only.</li>
          <li>Administered prices (petrol, diesel, electricity, gas) move in policy steps, not market
            drifts; metrics are reported split on that flag.</li>
        </ul>
        <p className="mt-4 rounded-lg bg-amber-50 p-3 text-sm font-semibold text-amber-900 ring-1 ring-amber-200">
          {t("methodology.notAdvice")}
        </p>
      </section>
    </div>
  );
}
