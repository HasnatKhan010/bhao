"use client";

import { useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import Link from "next/link";

import DirectionBadge from "@/components/DirectionBadge";
import FixtureBanner from "@/components/FixtureBanner";
import PriceChart from "@/components/PriceChart";
import { api, fmt, fmtRs, type Forecast } from "@/lib/api";

function useHealth() {
  const [isFixture, setIsFixture] = useState<boolean | null>(null);
  const [panelWeek, setPanelWeek] = useState<string | null>(null);
  useEffect(() => {
    fetch(`${process.env.NEXT_PUBLIC_BHAO_API_URL ?? "http://localhost:8000"}/api/health`)
      .then((r) => r.json())
      .then((b) => {
        setIsFixture(b.is_fixture);
        setPanelWeek(b.panel_week);
      })
      .catch(() => setIsFixture(null));
  }, []);
  return { isFixture, panelWeek };
}

export default function HomePage() {
  const t = useTranslations();
  const { isFixture, panelWeek } = useHealth();
  const [cities, setCities] = useState<{ city_code: string; city_en: string; city_ur: string; n_items: number }[]>([]);
  const [items, setItems] = useState<{ item_code: string; item_en: string; item_ur: string; unit_raw: string }[]>([]);
  const [city, setCity] = useState("");
  const [item, setItem] = useState("");
  const [forecast, setForecast] = useState<Forecast | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.cities().then((r) => {
      setCities(r.data.filter((c) => c.city_code !== "00"));
      const saved = localStorage.getItem("bhao_city");
      if (saved) setCity(saved);
    });
    api.items().then((r) => setItems(r.data));
  }, []);

  useEffect(() => {
    if (!city) return;
    localStorage.setItem("bhao_city", city);
    setForecast(null);
    if (item) {
      setBusy(true);
      api.forecast(city, item).then((r) => setForecast(r)).finally(() => setBusy(false));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [city]);

  useEffect(() => {
    if (!city || !item) return;
    setBusy(true);
    api.forecast(city, item).then((r) => setForecast(r)).finally(() => setBusy(false));
  }, [item, city]);

  const label = useMemo(() => {
    if (!city || !item || !forecast) return null;
    return {
      city: forecast.city_ur || forecast.city_en,
      item: forecast.item_ur || forecast.item_en,
    };
  }, [city, item, forecast]);

  const lastPrice = forecast?.last_actual ?? null;
  const prevPrice = forecast && forecast.history.length > 1
    ? forecast.history[forecast.history.length - 2]?.price_avg ?? null
    : null;
  const wow = lastPrice != null && prevPrice != null ? ((lastPrice - prevPrice) / prevPrice) * 100 : null;

  return (
    <div className="space-y-6">
      <FixtureBanner isFixture={isFixture} />

      <section className="text-center">
        <h1 className="text-3xl font-extrabold tracking-tight text-emerald-900 md:text-4xl">
          {t("home.tagline")}
        </h1>
        <p className="mx-auto mt-2 max-w-2xl text-slate-600">{t("home.subtitle")}</p>
        {panelWeek && (
          <p className="mt-1 text-xs text-slate-400">
            {t("common.panelWeek")}: {panelWeek}
          </p>
        )}
      </section>

      {/* the picker — two taps to an answer */}
      <section className="grid gap-3 sm:grid-cols-2">
        <label className="block">
          <span className="mb-1 block text-sm font-semibold text-slate-700">{t("common.chooseCity")}</span>
          <select
            value={city}
            onChange={(e) => setCity(e.target.value)}
            className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 shadow-sm focus:border-emerald-600 focus:outline-none"
          >
            <option value="">—</option>
            {cities.map((c) => (
              <option key={c.city_code} value={c.city_code}>
                {c.city_ur} · {c.city_en}
              </option>
            ))}
          </select>
        </label>
        <label className="block">
          <span className="mb-1 block text-sm font-semibold text-slate-700">{t("common.chooseItem")}</span>
          <select
            value={item}
            onChange={(e) => setItem(e.target.value)}
            className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 shadow-sm focus:border-emerald-600 focus:outline-none"
          >
            <option value="">—</option>
            {items.map((it) => (
              <option key={it.item_code} value={it.item_code}>
                {it.item_ur} · {it.item_en}
              </option>
            ))}
          </select>
        </label>
      </section>

      {busy && <p className="text-center text-slate-500">{t("common.loading")}</p>}

      {forecast && label && (
        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex items-start justify-between">
            <div>
              <h2 className="text-2xl font-bold">
                <span className="font-urdu">{label.item}</span>{" "}
                <span className="text-base font-medium text-slate-400">({forecast.unit_raw})</span>
              </h2>
              <p className="text-slate-500">
                <span className="font-urdu">{label.city}</span> · {forecast.city_en} — {forecast.city_ur}
              </p>
            </div>
            <DirectionBadge direction={forecast.direction} />
          </div>

          <div className="mt-5 grid grid-cols-1 gap-3 sm:grid-cols-3">
            <div className="rounded-xl bg-slate-50 p-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                {t("common.thisWeek")}
              </p>
              <p className="mt-1 text-2xl font-extrabold">{fmtRs(lastPrice)}</p>
              {wow != null && (
                <p className={`text-sm font-medium ${wow >= 0 ? "text-red-700" : "text-emerald-700"}`}>
                  {wow >= 0 ? "▲" : "▼"} {fmt(Math.abs(wow), 1)}% vs last week
                </p>
              )}
            </div>
            <div className="rounded-xl bg-emerald-50 p-4 ring-1 ring-emerald-200">
              <p className="text-xs font-semibold uppercase tracking-wide text-emerald-700">
                {t("common.nextWeek")} · {t("common.forecast")}
              </p>
              <p className="mt-1 text-2xl font-extrabold text-emerald-900">{fmtRs(forecast.p50)}</p>
              <p className="text-sm text-emerald-800">
                {t("common.range")}: {fmtRs(forecast.p10)} – {fmtRs(forecast.p90)}
              </p>
            </div>
            <div className="rounded-xl bg-amber-50 p-4 ring-1 ring-amber-200">
              <p className="text-xs font-semibold uppercase tracking-wide text-amber-700">
                {t("common.ourError", { n: 8 })}
              </p>
              <p className="mt-1 text-2xl font-extrabold text-amber-900">
                {forecast.recent_error.mae != null ? fmtRs(forecast.recent_error.mae) : "—"}
              </p>
              <p className="text-xs text-amber-800">MASE {forecast.recent_error.mase?.toFixed(2) ?? "—"}</p>
            </div>
          </div>

          {forecast.p50 == null && (
            <p className="mt-3 text-sm text-slate-500">{t("common.insufficientHistory")}</p>
          )}

          <div className="mt-6">
            <PriceChart history={forecast.history} unit={forecast.unit_raw} />
          </div>

          <div className="mt-4 flex flex-wrap gap-2 text-sm">
            <Link href={`/item/${forecast.item_code}`} className="text-emerald-700 underline-offset-2 hover:underline">
              {t("nav.home") === "Home" ? "All 17 cities for this item →" : "←"}
            </Link>
            <Link href={`/scorecard`} className="text-emerald-700 underline-offset-2 hover:underline">
              How wrong we&apos;ve been lately →
            </Link>
          </div>
        </section>
      )}
    </div>
  );
}
