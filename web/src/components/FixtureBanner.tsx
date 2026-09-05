"use client";

import { useTranslations } from "next-intl";

/** The guard that stops synthetic fixture prices ending up in a portfolio
 * screenshot. Shown whenever the API reports is_fixture. Not optional. */
export default function FixtureBanner({ isFixture }: { isFixture: boolean | null }) {
  const t = useTranslations("banner");
  if (!isFixture) return null;
  return (
    <div className="bg-amber-300 px-4 py-2 text-center text-sm font-semibold text-amber-950"
         role="alert" data-testid="fixture-banner">
      ⚠ {t("fixture")}
    </div>
  );
}
