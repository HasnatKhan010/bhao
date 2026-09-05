"use client";

import { useTranslations } from "next-intl";

const SCHEMA_ROWS: [string, string][] = [
  ["week_ending", "date — Thursday the survey covers"],
  ["city_code", "string \"01\"–\"17\", \"00\" = national"],
  ["city_en / city_ur", "bilingual city labels"],
  ["item_code", "string \"001\"–\"999\", Bhao's stable id"],
  ["item_en / item_ur", "bilingual commodity labels"],
  ["unit_raw", "exactly as PBS printed it, e.g. \"20 Kg\""],
  ["unit_norm / qty_norm", "normalised unit + quantity, e.g. kg / 20.0"],
  ["price_min / price_avg / price_max", "PKR, null = not surveyed"],
  ["price_per_unit", "price_avg / qty_norm — comparable across pack sizes"],
  ["source / source_url", "which file this row came from"],
  ["ingested_at", "when Bhao read it (UTC)"],
  ["revision", "0 = first publication; 1+ = PBS restated it"],
];

export default function DataPage() {
  const t = useTranslations();
  const api = process.env.NEXT_PUBLIC_BHAO_API_URL ?? "http://localhost:8000";

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">{t("data.title")}</h1>
      <p className="max-w-3xl text-slate-600">{t("data.intro")}</p>

      <div className="flex flex-wrap gap-3">
        <a href={`${api}/api/download/panel.parquet`}
           className="rounded-lg bg-emerald-700 px-5 py-2.5 font-semibold text-white hover:bg-emerald-800">
          ⬇ {t("data.parquet")}
        </a>
        <a href={`${api}/api/download/panel.csv`}
           className="rounded-lg bg-white px-5 py-2.5 font-semibold text-emerald-800 ring-1 ring-emerald-700 hover:bg-emerald-50">
          ⬇ {t("data.csv")}
        </a>
      </div>

      <section>
        <h2 className="mb-2 text-lg font-semibold">{t("data.schema")}</h2>
        <div className="overflow-x-auto rounded-xl bg-white shadow-sm">
          <table className="w-full text-sm">
            <tbody>
              {SCHEMA_ROWS.map(([col, desc]) => (
                <tr key={col} className="border-b border-slate-100 last:border-0">
                  <td className="whitespace-nowrap px-3 py-2 font-mono text-xs text-emerald-800">{col}</td>
                  <td className="px-3 py-2 text-slate-600">{desc}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section>
        <h2 className="mb-2 text-lg font-semibold">{t("data.licence")}</h2>
        <p className="text-sm text-slate-600">{t("data.cite")}</p>
        <p className="mt-2 text-sm text-slate-600">
          Source: Pakistan Bureau of Statistics, Weekly Sensitive Price Indicator (public official
          statistics). Every row carries its source URL. WFP/HDX monthly prices are a separate,
          pre-existing dataset used for long-history validation, attributed and labelled as such.
        </p>
      </section>
    </div>
  );
}
