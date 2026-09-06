import { Inter, Noto_Nastaliq_Urdu } from "next/font/google";
import { NextIntlClientProvider } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";
import { notFound } from "next/navigation";

import FixtureBanner from "@/components/FixtureBanner";
import Header from "@/components/Header";
import PWARegister from "@/components/PWARegister";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });
const nastaliq = Noto_Nastaliq_Urdu({
  subsets: ["arabic"],
  variable: "--font-nastaliq",
  weight: ["400", "500", "600", "700"],
});

export function generateStaticParams() {
  return [{ locale: "en" }, { locale: "ur" }];
}

export default async function LocaleLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  if (locale !== "en" && locale !== "ur") notFound();
  setRequestLocale(locale);
  const messages = await getMessages();
  const rtl = locale === "ur";

  return (
    <html lang={locale} dir={rtl ? "rtl" : "ltr"}
          className={`${inter.variable} ${nastaliq.variable}`}>
      <body className="min-h-screen bg-slate-50 text-slate-900 antialiased"
            style={rtl ? { fontFamily: "var(--font-nastaliq)", lineHeight: "1.9" } : { fontFamily: "var(--font-inter)" }}>
        <NextIntlClientProvider messages={messages}>
          <PWARegister />
          {/* Fixture banner is client-driven via /api/health on the home page;
              the header renders immediately, the banner pops in when meta lands. */}
          <div id="banner-root" />
          <Header />
          <main className="mx-auto max-w-5xl px-4 py-8">{children}</main>
          <footer className="safe-bottom border-t border-slate-200 bg-white py-6 text-center text-sm text-slate-500">
            <p>
              بھاؤ · Bhao — public prices from the Pakistan Bureau of Statistics, weekly SPI.
            </p>
            <p className="mt-1 text-xs">
              Not financial advice · forecasts carry their own error record ·{" "}
              <a href={`/${locale}/privacy`} className="underline hover:text-emerald-700">
                Privacy
              </a>
            </p>
          </footer>
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
