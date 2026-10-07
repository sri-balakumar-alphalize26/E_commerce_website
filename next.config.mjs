import { execSync } from "node:child_process";
import { readFileSync } from "node:fs";

/* Which code is running, fixed into the page when it is built: the footer
   shows it, so after a deploy anyone can see whether the new build is live.
   No git on the build machine (a zip deploy) just leaves the commit blank. */
const pkg = JSON.parse(readFileSync(new URL("./package.json", import.meta.url), "utf8"));
const git = (args) => { try { return execSync(`git ${args}`, { stdio: ["ignore", "pipe", "ignore"] }).toString().trim(); } catch { return ""; } };

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,

  env: {
    NEXT_PUBLIC_APP_VERSION: pkg.version || "",
    NEXT_PUBLIC_APP_BUILD: git("rev-parse --short HEAD"),
    NEXT_PUBLIC_APP_COMMIT: git("rev-parse HEAD"),
    NEXT_PUBLIC_APP_BUILT: new Date().toISOString(),
  },

  /* A production build can live beside the dev server's `.next` without
     touching it: NEXT_DIST_DIR=.next-demo for both `next build` and
     `next start`. Sharing `.next` with a running `next dev` overwrites its
     chunks and silently stops the page hydrating. */
  distDir: process.env.NEXT_DIST_DIR || ".next",

  /* Product pictures come back from Odoo as short, relative addresses like
     /web/image/product.template/13/image_512/512x512 — which the browser then
     asks this app for, not Odoo. Passing them through is what makes that work,
     and it is what the "Image address" setting in Odoo assumes when it is left
     empty: "the app then gets short addresses and loads them through itself."

     They used to be rewrites here. They are route handlers now (app/web/image,
     app/web/assets, app/369mart/variant/photo, all via odooPassthrough in
     lib/odoo.js) because a rewrite cannot tell Odoo which database ODOO_DB
     names. Same idea as before: one origin, no CORS, and Odoo's address never
     reaches the browser. */
};

export default nextConfig;
