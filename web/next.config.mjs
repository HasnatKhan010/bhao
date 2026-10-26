import createNextIntlPlugin from "next-intl/plugin";

const withNextIntl = createNextIntlPlugin("./src/i18n/request.ts");

/** @type {import('next').NextConfig} */
const isStaticExport = process.env.STATIC_EXPORT === "1";
// GitHub Pages serves the app at /<repo-name>/; set NEXT_PUBLIC_BHAO_BASE_PATH=/bhao at build time.
const basePath = process.env.NEXT_PUBLIC_BHAO_BASE_PATH || "";

const nextConfig = {
  // standalone = the deployed web server; export = the bundled Capacitor app
  output: isStaticExport ? "export" : "standalone",
  ...(isStaticExport
    ? {
        images: { unoptimized: true },
        basePath,
        assetPrefix: basePath,
      }
    : {}),
  async rewrites() {
    // rewrites are not supported in static export mode
    if (isStaticExport) return [];
    const api = process.env.BHAO_API_URL || "http://localhost:8000";
    return [
      { source: "/api-docs-proxy/:path*", destination: `${api}/:path*` },
      { source: "/api/:path*", destination: `${api}/api/:path*` },
    ];
  },
};

export default withNextIntl(nextConfig);
