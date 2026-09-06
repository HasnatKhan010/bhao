import { getTranslations, setRequestLocale } from "next-intl/server";

export default async function PrivacyPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("privacy");

  const items: Array<[string, string]> = [
    ["", t("collect")],
    ["", t("storage")],
    ["", t("server")],
    ["", t("data")],
    ["", t("contact")],
  ];

  return (
    <div className="max-w-3xl space-y-6">
      <h1 className="text-2xl font-bold">{t("title")}</h1>
      {items.map(([_, text], i) => (
        <p key={i} className="text-sm leading-relaxed text-slate-700">
          {text}
        </p>
      ))}
    </div>
  );
}
