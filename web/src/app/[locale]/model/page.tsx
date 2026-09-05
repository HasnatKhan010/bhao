"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";

import { api, fmt } from "@/lib/api";

export default function ModelPage() {
  const t = useTranslations();
  const [reg, setReg] = useState<any>(null);

  useEffect(() => {
    api.model().then((r) => setReg(r.data)).catch(() => {});
  }, []);

  if (!reg) return <p className="text-slate-500">Loading…</p>;
  const champ = reg.models?.find((m: any) => m.status === "champion") ?? reg.models?.[0];
  const bt = champ?.backtest ?? {};

  return (
    <div className="space-y-8">
      <h1 className="text-2xl font-bold">{t("model.title")}</h1>
      <p className="max-w-3xl text-slate-600">{t("model.intro")}</p>

      <section className="rounded-2xl border border-slate-200 bg-white p-5">
        <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{t("model.champion")}</p>
        <p className="mt-1 text-2xl font-extrabold text-emerald-800">{reg.champion}</p>
        {champ?.promoted_because && <p className="mt-2 text-sm text-slate-600">{champ.promoted_because}</p>}
        <div className="mt-4 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
          <div><span className="text-slate-400">MASE</span><p className="font-bold">{bt.mase != null ? fmt(bt.mase, 3) : "—"}</p></div>
          <div><span className="text-slate-400">sMAPE</span><p className="font-bold">{bt.smape != null ? `${fmt(bt.smape, 2)}%` : "—"}</p></div>
          <div><span className="text-slate-400">coverage@80</span><p className="font-bold">{bt.coverage_80 != null ? `${fmt(bt.coverage_80 * 100, 0)}%` : "—"}</p></div>
          <div><span className="text-slate-400">folds</span><p className="font-bold">{bt.folds ?? "—"}</p></div>
        </div>
      </section>

      <section>
        <h2 className="mb-2 text-lg font-semibold">{t("model.promotions")}</h2>
        <div className="space-y-2">
          {(reg.promotion_log ?? []).map((p: any, i: number) => (
            <div key={i} className="rounded-xl border border-slate-200 bg-white p-4 text-sm">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-xs text-slate-400">{p.at}</span>
                <span className="font-mono">{p.from ?? "—"} → {p.to}</span>
                <span className={`rounded-full px-2 py-0.5 text-xs font-bold ${p.decision === "promote" ? "bg-emerald-100 text-emerald-800" : "bg-slate-200 text-slate-700"}`}>
                  {p.decision}
                </span>
                {p.trigger && <span className="text-xs text-slate-400">trigger: {p.trigger}</span>}
              </div>
              <p className="mt-1 text-slate-600">{p.reason}</p>
            </div>
          ))}
          {!(reg.promotion_log ?? []).length && <p className="text-sm text-slate-400">No promotions yet.</p>}
        </div>
      </section>
    </div>
  );
}
