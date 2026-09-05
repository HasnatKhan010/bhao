"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { useParams } from "next/navigation";

import { api, fmtRs } from "@/lib/api";

/** Every item in one city: table + movers of the week. */
export default function CityPage() {
  const t = useTranslations();
  const { code } = useParams<{ code: string }>();
  const [cities, setCities] = useState<{ city_code: string; city_en: string; city_ur: string }[]>([]);
  const [items, setItems] = useState<{ item_code: string; item_en: string; item_ur: string; unit_raw: string }[]>([]);
  const [rows, setRows] = useState<Record<string, any>>({});

  useEffect(() => {
    api.cities().then((r) => setCities(r.data.filter((c) => c.city_code !== "00")));
    api.items().then((r) => setItems(r.data));
  }, []);

  useEffect(() => {
    if (!code) return;
    Promise.all(
      items.map((it) =>
        api.forecast(code, it.item_code).then((r) => ({ item: it.item_code, data: r.data })).catch(() => null)
      )
    ).then((all) => {
      const m: Record<string, any> = {};
      all.forEach((x) => { if (x) m[x.item] = x.data; });
      setRows(m);
    });
  }, [code, items]);

  const city = cities.find((c) => c.city_code === code);
  const withData = items.filter((i) => rows[i.item_code]);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">
        {city ? `${city.city_ur} · ${city.city_en}` : code}
      </h1>
      <table className="w-full border-collapse overflow-hidden rounded-xl bg-white text-sm shadow-sm">
        <thead>
          <tr className="bg-slate-100 text-left">
            <th className="px-3 py-2 font-semibold">{t("common.chooseItem")}</th>
            <th className="px-3 py-2 font-semibold">{t("common.thisWeek")}</th>
            <th className="px-3 py-2 font-semibold">{t("common.nextWeek")}</th>
          </tr>
        </thead>
        <tbody>
          {withData.map((it) => {
            const f = rows[it.item_code];
            return (
              <tr key={it.item_code} className="border-t border-slate-100">
                <td className="px-3 py-2">
                  <Link href={`/item/${it.item_code}`} className="text-emerald-700 hover:underline">
                    {it.item_ur} · {it.item_en}
                  </Link>
                  <span className="ml-1 text-xs text-slate-400">({it.unit_raw})</span>
                </td>
                <td className="px-3 py-2">{fmtRs(f.last_actual)}</td>
                <td className="px-3 py-2 font-semibold">{fmtRs(f.p50)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
