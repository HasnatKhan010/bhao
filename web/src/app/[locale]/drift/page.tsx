"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";

import { api } from "@/lib/api";

export default function DriftPage() {
  const t = useTranslations();
  const [rows, setRows] = useState<Awaited<ReturnType<typeof api.drift>>["data"]>([]);

  useEffect(() => {
    api.drift().then((r) => setRows(r.data)).catch(() => {});
  }, []);

  const sevStyle: Record<string, string> = {
    critical: "bg-red-100 text-red-800",
    warn: "bg-amber-100 text-amber-800",
    info: "bg-slate-100 text-slate-600",
  };

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">{t("drift.title")}</h1>
      <p className="max-w-3xl text-slate-600">{t("drift.intro")}</p>
      <div className="space-y-3">
        {rows.map((r, i) => (
          <div key={i} className={`rounded-xl border p-4 ${r.fired ? "border-red-200 bg-red-50/60" : "border-slate-200 bg-white"}`}>
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <span className="font-mono text-xs text-slate-400">{r.checked_on}</span>
              <span className="rounded-full bg-slate-200 px-2 py-0.5 text-xs font-semibold">{r.channel}</span>
              <span className="rounded-full bg-slate-200 px-2 py-0.5 text-xs font-semibold">{r.test}</span>
              <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${sevStyle[r.severity] ?? sevStyle.info}`}>
                {r.severity}
              </span>
              {r.fired && (
                <span className="rounded-full bg-red-600 px-2 py-0.5 text-xs font-bold text-white">FIRED</span>
              )}
            </div>
            <p className="mt-2 font-mono text-xs text-slate-500">
              {r.subject} · stat {r.statistic?.toFixed(3) ?? "—"} / threshold {r.threshold?.toFixed(3) ?? "—"}
            </p>
            <p className="mt-1 text-sm text-slate-700">{r.note}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
