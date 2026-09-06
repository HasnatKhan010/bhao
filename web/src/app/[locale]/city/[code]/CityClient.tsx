"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { useParams } from "next/navigation";

import { api, fmtRs, type ForecastRow } from "@/lib/api";

/** Every item in one city: latest actual + next-week forecast, in TWO requests. */
export default function CityPage() {
  const t = useTranslations();
  const { code } = useParams<{ code: string }>();
  const [cities, setCities] = useState<{ city_code: string; city_en: string; city_ur: string }[]>([]);
  const [rows, setRows] = useState<ForecastRow[]>([]);
  const [latest, setLatest] = useState<Record<string, number | null>>({});

  useEffect(() => {
    api.cities().then((r) => setCities(r.data.filter((c) => c.city_code !== "00")));
  }, []);

  useEffect(() => {
    if (!code) return;
    api.forecastsBulk({ city_code: code }).then((r) => setRows(r.data)).catch(() => setRows([]));
    api
      .prices({ city_code: code, limit: 400 })
      .then((r) => {
        const m: Record<string, number | null> = {};
        for (const row of r.data) {
          if (!(row.item_code in m)) m[row.item_code] = row.price_avg; // rows arrive week DESC
        }
        setLatest(m);
      })
      .catch(() => {});
  }, [code]);

  const city = cities.find((c) => c.city_code === code);
  const items = rows.map((r) => ({
    code: r.item_code,
    ur: r.item_ur ?? r.item_code,
    en: r.item_en ?? r.item_code,
    last: latest[r.item_code] ?? null,
    p50: r.p50,
  }));

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">
        {city ? `${city.city_ur} · ${city.city_en}` : code}
      </h1>
      <table className="w-full border-collapse overflow-hidden rounded-xl bg-white text-sm shadow-sm">
        <thead>
          <tr className="bg-slate-100 text-start">
            <th className="px-3 py-2 font-semibold">{t("common.chooseItem")}</th>
            <th className="px-3 py-2 font-semibold">{t("common.thisWeek")}</th>
            <th className="px-3 py-2 font-semibold">{t("common.nextWeek")}</th>
          </tr>
        </thead>
        <tbody>
          {items.map((it) => (
            <tr key={it.code} className="border-t border-slate-100">
              <td className="px-3 py-2">
                <Link href={`/item/${it.code}`} className="text-emerald-700 hover:underline">
                  {it.ur} · {it.en}
                </Link>
              </td>
              <td className="px-3 py-2">{fmtRs(it.last)}</td>
              <td className="px-3 py-2 font-semibold">{fmtRs(it.p50)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {!rows.length && <p className="text-sm text-slate-500">{t("common.loading")}</p>}
    </div>
  );
}
