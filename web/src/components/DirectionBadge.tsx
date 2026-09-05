"use client";

import { useTranslations } from "next-intl";

/** Direction badge: up/down/flat, decided by the API against the series' own
 * recent MAE — never by a fixed percentage. */
export default function DirectionBadge({
  direction,
}: {
  direction: "up" | "down" | "flat";
}) {
  const t = useTranslations("common.direction");
  const styles: Record<string, string> = {
    up: "bg-red-100 text-red-800",
    down: "bg-emerald-100 text-emerald-800",
    flat: "bg-slate-100 text-slate-700",
  };
  const arrow: Record<string, string> = { up: "▲", down: "▼", flat: "▬" };
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-sm font-semibold ${styles[direction]}`}>
      <span aria-hidden>{arrow[direction]}</span>
      {t(direction)}
    </span>
  );
}
