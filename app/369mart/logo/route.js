/* The shop's logo: the one uploaded in the console (Settings > Store), served
   by Odoo at /369mart/logo - the same picture the WhatsApp and payment pages
   show. None uploaded, or the shop not reachable: the logo that ships with the
   website. */
import { odooPassthrough } from "@/lib/odoo";

export const dynamic = "force-dynamic";

export async function GET(req) {
  const res = await odooPassthrough(req, "/369mart/logo");
  if (!(res.ok || res.status === 304)) {
    return Response.redirect(new URL("/brand/369mart-logo-clear.png", req.url), 302);
  }
  /* The site asks without a version, so keep it short: a new logo shows
     within five minutes. */
  const headers = new Headers(res.headers);
  headers.set("cache-control", "public, max-age=300");
  return new Response(res.body, { status: res.status, headers });
}
