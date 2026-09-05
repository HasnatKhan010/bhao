"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { useParams } from "next/navigation";

import PriceChart from "@/components/PriceChart";
import { api, fmtRs, type ForecastRow } from "@/lib/api";

/** One item across all 17 cities: chart + city table, in THREE requests. */
export default function ItemPage() {
  const t = useTranslations();
  const { code } = useParams<{ code: string }>();
  const [items, setItems] = useState<{ item_code: string; item_en: string; item_ur: string; unit_raw: string }[]>([]);
  const [cities, setCities] = useState<{ city_code: string; city_en: string; city_ur: string }[]>([]);
  const [rows, setRows] = useState<ForecastRow[]>([]);
  const [latest, setLatest] = useState<Record<string, number | null>>({});
  const [chart, setChart] = useState<{ week_ending: string; price_avg: number | null }[]>([]);
  const [unit, setUnit] = useState("");

  useEffect(() => {
    api.items().then((r) => setItems(r.data));
    api.cities().then((r) => setCities(r.data.filter((c) => c.city_code !== "00")));
  }, []);

  useEffect(() => {
    if (!code) return;
    api.forecastsBulk({ item_code: code }).then((r) => setRows(r.data)).catch(() => setRows([]));
    api
      .prices({ item_code: code, limit: 400 })
      .then((r) => {
        const m: Record<string, number | null> = {};
        for (const row of r.data) {
          if (!(row.city_code in m)) m[row.city_code] = row.price_avg;
        }
        setLatest(m);
      })
      .catch(() => {});
    // one representative series for the chart (Lahore)
    api
      .forecast("05", code)
      .then((r) => {
        setChart(r.history);
        setUnit(r.unit_raw);
      })
      .catch(() => {});
  }, [code]);

  const item = items.find((i) => i.item_code === code);
  const cityById = new Map(cities.map((c) => [c.city_code, c]));
  const ordered = cities
    .map((c) => rows.find((r) => r.city_code === c.city_code))
    .filter((r): r is ForecastRow => Boolean(r));

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">
        {item ? `${item.item_ur} · ${item.item_en}` : code}
        {item && <span className="ms-2 text-sm font-normal text-slate-400">({item.unit_raw})</span>}
      </h1>

      {chart.length > 0 && <PriceChart history={chart} unit={unit || item?.unit_raw || ""} />}

      <table className="w-full border-collapse overflow-hidden rounded-xl bg-white text-sm shadow-sm">
        <thead>
          <tr className="bg-slate-100 text-start">
            <th className="px-3 py-2 font-semibold">{t("common.chooseCity")}</th>
            <th className="px-3 py-2 font-semibold">{t("common.thisWeek")}</th>
            <th className="px-3 py-2 font-semibold">{t("common.nextWeek")}</th>
          </tr>
        </thead>
        <tbody>
          {ordered.map((r) => {
            const c = cityById.get(r.city_code);
            return (
              <tr key={r.city_code} className="border-t border-slate-100">
                <td className="px-3 py-2">
                  <Link href={`/city/${r.city_code}`} className="text-emerald-700 hover:underline">
                    {c ? `${c.city_ur} · ${c.city_en}` : r.city_code}
                  </Link>
                </td>
                <td className="px-3 py-2">{fmtRs(latest[r.city_code] ?? null)}</td>
                <td className="px-3 py-2 font-semibold">{fmtRs(r.p50)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="text-xs text-slate-400">{t("common.notSurveyed")} = no row = the sheet printed &#8220;-&#8221;.</p>
    </div>
  );
}
