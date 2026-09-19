const ODOO_URL = (process.env.ODOO_URL || "http://localhost:8097").replace(/\/$/, "");

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,

  /* Product pictures come back from Odoo as short, relative addresses like
     /web/image/product.template/13/image_512/512x512 — which the browser then
     asks this app for, not Odoo. Passing them through is what makes that work,
     and it is what the "Image address" setting in Odoo assumes when it is left
     empty: "the app then gets short addresses and loads them through itself."

     Doing it here rather than sending absolute URLs keeps every request on one
     origin, so there is no CORS to arrange and Odoo's address never reaches the
     browser. Fill in that setting only when this passthrough is not possible. */
  async rewrites() {
    return [
      { source: "/web/image/:path*", destination: `${ODOO_URL}/web/image/:path*` },
      { source: "/web/assets/:path*", destination: `${ODOO_URL}/web/assets/:path*` },
    ];
  },
};

export default nextConfig;
