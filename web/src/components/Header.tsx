"use client";

import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import { useParams } from "next/navigation";
import { useState } from "react";

export default function Header() {
  const t = useTranslations("nav");
  const locale = useLocale();
  const params = useParams<{ locale: string }>();
  const [open, setOpen] = useState(false);

  const links = [
    ["/", t("home")],
    ["/movers", t("movers")],
    ["/scorecard", t("scorecard")],
    ["/drift", t("drift")],
    ["/model", t("model")],
    ["/data", t("data")],
    ["/methodology", t("methodology")],
  ];
  const other = locale === "ur" ? "en" : "ur";
  const prefix = `/${params.locale}`;

  return (
    <header className="border-b border-slate-200 bg-white">
      <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-3">
        <Link href={prefix + "/"} className="text-xl font-extrabold tracking-tight text-emerald-800">
          بھاؤ <span className="text-slate-400">/</span> Bhao
        </Link>
        <nav className="hidden items-center gap-5 text-sm font-medium text-slate-600 md:flex">
          {links.map(([href, label]) => (
            <Link key={href} href={prefix + href} className="hover:text-emerald-700">
              {label}
            </Link>
          ))}
        </nav>
        <div className="flex items-center gap-2">
          <Link
            href={`/${other}${typeof window !== "undefined" ? window.location.pathname.replace(/^\/(en|ur)/, "") : ""}`}
            className="rounded-full border border-slate-300 px-3 py-1 text-sm hover:border-emerald-600 hover:text-emerald-700"
          >
            {other === "ur" ? "اردو" : "English"}
          </Link>
          <button
            className="rounded border border-slate-300 px-2 py-1 text-sm md:hidden"
            onClick={() => setOpen(!open)}
            aria-label="menu"
          >
            ☰
          </button>
        </div>
      </div>
      {open && (
        <nav className="flex flex-col gap-2 px-4 pb-4 text-sm md:hidden">
          {links.map(([href, label]) => (
            <Link key={href} href={prefix + href} onClick={() => setOpen(false)}>
              {label}
            </Link>
          ))}
        </nav>
      )}
    </header>
  );
}
