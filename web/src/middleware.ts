import createMiddleware from "next-intl/middleware";

export default createMiddleware({
  locales: ["en", "ur"],
  defaultLocale: "en",
  localePrefix: "always",
});

export const config = {
  matcher: ["/((?!api|api-docs|_next|_vercel|.*\\..*).*)"],
};
