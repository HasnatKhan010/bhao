"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import Link from "next/link";

import { api, fmt } from "@/lib/api";

export default function MoversPage() {
  const t = useTranslations();
  const [rows, setRows] = useState<Awaited<ReturnType<typeof api.movers>>["data"]>([]);
  const [dir, setDir] = useState<"both" | "up" | "down">("both");

  useEffect(() => {
    api.movers(15, dir).then((r) => setRows(r.data)).catch(() => {});
  }, [dir]);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">{t("movers.title")}</h1>
      <p className="text-slate-600">{t("movers.intro")}</p>
      <div className="flex gap-2">
        {(["both", "up", "down"] as const).map((d) => (
          <button
            key={d}
            onClick={() => setDir(d)}
            className={`rounded-full px-4 py-1.5 text-sm font-medium ${
              dir === d ? "bg-emerald-700 text-white" : "bg-white text-slate-600 ring-1 ring-slate-300"
            }`}
          >
            {d}
          </button>
        ))}
      </div>
      <table className="w-full border-collapse overflow-hidden rounded-xl bg-white text-sm shadow-sm">
        <thead>
          <tr className="bg-slate-100 text-left">
            <th className="px-3 py-2 font-semibold">#</th>
            <th className="px-3 py-2 font-semibold">{t("movers.item")}</th>
            <th className="px-3 py-2 font-semibold">{t("movers.price")}</th>
            <th className="px-3 py-2 font-semibold">{t("movers.change")}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.item_code} className="border-t border-slate-100">
              <td className="px-3 py-2 text-slate-400">{r.rank}</td>
              <td className="px-3 py-2">
                <Link href={`/item/${r.item_code}`} className="text-emerald-700 hover:underline">
                  {r.item_ur} · {r.item_en}
                </Link>
              </td>
              <td className="px-3 py-2">{fmt(r.price_avg)}</td>
              <td className={`px-3 py-2 font-semibold ${(r.pct_change ?? 0) >= 0 ? "text-red-700" : "text-emerald-700"}`}>
                {r.pct_change != null ? `${r.pct_change >= 0 ? "+" : ""}${fmt(r.pct_change, 1)}%` : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
