import createNextIntlPlugin from "next-intl/plugin";

const withNextIntl = createNextIntlPlugin("./src/i18n/request.ts");

/** @type {import('next').NextConfig} */
const isStaticExport = process.env.STATIC_EXPORT === "1";
const nextConfig = {
  // standalone = the deployed web server; export = the bundled Capacitor app
  output: isStaticExport ? "export" : "standalone",
  ...(isStaticExport ? { images: { unoptimized: true } } : {}),
  async rewrites() {
    const api = process.env.BHAO_API_URL || "http://localhost:8000";
    return [
      { source: "/api-docs-proxy/:path*", destination: `${api}/:path*` },
      { source: "/api/:path*", destination: `${api}/api/:path*` },
    ];
  },
};

export default withNextIntl(nextConfig);
