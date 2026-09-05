"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import Link from "next/link";

import { api, fmt } from "@/lib/api";

/** Live accuracy. MASE by item, coverage, bias, and where naive still wins.
 * Never behind a tab — the front page links straight here. */
export default function ScorecardPage() {
  const t = useTranslations();
  const [overall, setOverall] = useState<Awaited<ReturnType<typeof api.scorecard>>["data"]>([]);
  const [byItem, setByItem] = useState<Awaited<ReturnType<typeof api.scorecard>>["data"]>([]);
  const [items, setItems] = useState<{ item_code: string; item_ur: string; item_en: string }[]>([]);

  useEffect(() => {
    api.scorecard("overall", 100).then((r) => setOverall(r.data)).catch(() => {});
    api.scorecard("item", 2000).then((r) => setByItem(r.data)).catch(() => {});
    api.items().then((r) => setItems(r.data));
  }, []);

  const byModel: Record<string, typeof overall> = {};
  overall.forEach((r) => {
    (byModel[r.model_name] ??= []).push(r);
  });

  const itemNames = new Map(items.map((i) => [i.item_code, `${i.item_ur} · ${i.item_en}`]));
  const gbm = (byItem ?? []).filter((r) => r.model_name === "global_gbm").slice(0, 60);

  return (
    <div className="space-y-8">
      <h1 className="text-2xl font-bold">{t("scorecard.title")}</h1>
      <p className="max-w-3xl text-slate-600">{t("scorecard.intro")}</p>

      <section>
        <h2 className="mb-2 text-lg font-semibold">{t("scorecard.mase")} — {t("scorecard.model")}</h2>
        <table className="w-full border-collapse overflow-hidden rounded-xl bg-white text-sm shadow-sm">
          <thead>
            <tr className="bg-slate-100 text-left">
              <th className="px-3 py-2 font-semibold">{t("scorecard.model")}</th>
              <th className="px-3 py-2 font-semibold">{t("scorecard.mase")}</th>
              <th className="px-3 py-2 font-semibold">{t("scorecard.smape")} %</th>
              <th className="px-3 py-2 font-semibold">{t("scorecard.mae")}</th>
              <th className="px-3 py-2 font-semibold">{t("scorecard.coverage")}</th>
              <th className="px-3 py-2 font-semibold">{t("scorecard.bias")}</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(byModel)
              .sort((a, b) => (a[1][0]?.mase ?? 9) - (b[1][0]?.mase ?? 9))
              .map(([name, rows]) => {
                const latest = rows[0];
                return (
                  <tr key={name} className="border-t border-slate-100">
                    <td className="px-3 py-2 font-medium">{name}</td>
                    <td className="px-3 py-2">{latest?.mase != null ? fmt(latest.mase, 3) : "—"}</td>
                    <td className="px-3 py-2">{latest?.smape != null ? fmt(latest.smape, 2) : "—"}</td>
                    <td className="px-3 py-2">{latest?.mae != null ? fmt(latest.mae, 0) : "—"}</td>
                    <td className="px-3 py-2">
                      {latest?.coverage_80 != null ? `${fmt(latest.coverage_80 * 100, 0)}%` : "—"}
                    </td>
                    <td className="px-3 py-2">{latest?.bias != null ? fmt(latest.bias, 1) : "—"}</td>
                  </tr>
                );
              })}
          </tbody>
        </table>
      </section>

      <section>
        <h2 className="mb-2 text-lg font-semibold">
          {t("scorecard.mase")} {t("scorecard.maseRw") !== "MASE vs last-week" ? t("scorecard.maseRw") : "per commodity (champion)"}
        </h2>
        <table className="w-full border-collapse overflow-hidden rounded-xl bg-white text-sm shadow-sm">
          <thead>
            <tr className="bg-slate-100 text-left">
              <th className="px-3 py-2 font-semibold">commodity</th>
              <th className="px-3 py-2 font-semibold">MASE</th>
              <th className="px-3 py-2 font-semibold">MASE vs last wk</th>
              <th className="px-3 py-2 font-semibold">{t("scorecard.coverage")}</th>
              <th className="px-3 py-2 font-semibold">n</th>
            </tr>
          </thead>
          <tbody>
            {gbm.map((r) => (
              <tr key={r.item_code ?? r.target_week} className="border-t border-slate-100">
                <td className="px-3 py-2">
                  {r.item_code ? (
                    <Link href={`/item/${r.item_code}`} className="text-emerald-700 hover:underline">
                      {itemNames.get(r.item_code) ?? r.item_code}
                    </Link>
                  ) : "—"}
                </td>
                <td className="px-3 py-2">{r.mase != null ? fmt(r.mase, 2) : "—"}</td>
                <td className="px-3 py-2">{r.mase_rw != null ? fmt(r.mase_rw, 2) : "—"}</td>
                <td className="px-3 py-2">{r.coverage_80 != null ? `${fmt(r.coverage_80 * 100, 0)}%` : "—"}</td>
                <td className="px-3 py-2">{r.n_obs}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="mt-2 text-xs text-slate-400">{t("scorecard.naiveWins")}: MASE &gt; 1 means seasonal-naive won that commodity. It is shown, not hidden.</p>
      </section>
    </div>
  );
}
