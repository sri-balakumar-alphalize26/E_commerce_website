/* Server-side only: the storefront's route handlers talk to Odoo through this.
   The browser never sees ODOO_URL or Odoo's session cookie.

   Which Odoo and which database come from .env.local and nothing else:
     ODOO_URL=http://localhost:8069
     ODOO_DB=sparenix_test
   Change them and restart. No fallback address: a shop pointed at nothing says
   so, rather than quietly showing some other database's products.

   ODOO_DB travels as Odoo's X-Odoo-Database header, so one Odoo holding many
   databases can serve this shop without a --db-filter. Odoo accepts the header
   next to a session cookie only when both name the same database; a cookie from
   another database (ODOO_DB was changed) is answered 403, read here as signed out. */

const ODOO_URL = (process.env.ODOO_URL || "").trim().replace(/\/$/, "");
const ODOO_DB = (process.env.ODOO_DB || "").trim();
export const SESSION_COOKIE = "mart_session";

const NOT_CONNECTED = "Store not connected. Set ODOO_URL in .env.local and restart.";
if (!ODOO_URL) console.error(`[369mart] ${NOT_CONNECTED}`);

function odooHeaders(base, session) {
  const headers = { ...base };
  if (ODOO_DB) headers["X-Odoo-Database"] = ODOO_DB;
  if (session) headers.Cookie = `session_id=${session}`;
  return headers;
}

/* A brand-new Odoo session already tied to ODOO_DB. Sign-in and sign-up need
   one: a header-only request is stateless in Odoo, so the session they create
   would never be saved. /web/login?db= is Odoo's own way to pick a database. */
async function freshSession() {
  try {
    const r = await fetch(`${ODOO_URL}/web/login?db=${encodeURIComponent(ODOO_DB)}`, {
      cache: "no-store", redirect: "manual",
    });
    const m = (r.headers.get("set-cookie") || "").match(/session_id=([^;]+)/);
    return m ? m[1] : null;
  } catch (e) {
    return null;
  }
}

/* `fresh`: start from a session bound to ODOO_DB (sign-in, sign-up). */
export async function odooFetch(path, { method = "GET", body, session, fresh } = {}) {
  if (!ODOO_URL) return { status: 503, data: { ok: false, error: NOT_CONNECTED }, session: null };
  let started = null;
  if (fresh && !session && ODOO_DB) {
    started = await freshSession();
    if (!started) return { status: 503, data: { ok: false, error: "Can't reach the store. Try again in a moment." }, session: null };
  }
  const sent = session || started;
  const headers = odooHeaders({ "Content-Type": "application/json", Accept: "application/json" }, sent);
  let r;
  try {
    r = await fetch(ODOO_URL + path, {
      method, headers, body: body ? JSON.stringify(body) : undefined,
      cache: "no-store", redirect: "manual",
    });
  } catch (e) {
    return { status: 503, data: { ok: false, error: "Can't reach the store. Try again in a moment." }, session: null };
  }
  const m = (r.headers.get("set-cookie") || "").match(/session_id=([^;]+)/);
  const location = r.headers.get("location") || "";
  let data = null;
  try { data = await r.json(); } catch (e) {}
  let status = r.status;
  if (status >= 300 && status < 400) {
    /* Two very different things arrive as a redirect. A route that needs a
       signed-in customer answers 303 to /web/login when the session is missing
       or stale — that is simply "signed out". Anything else means Odoo did not
       know which database to use. Callers tell them apart with `location`. */
    data = /\/web\/login/.test(location)
      ? { ok: false, error: "Please sign in again." }
      : { ok: false, error: "The account server is not configured for this store." };
  } else if (status === 403 && session && !data) {
    /* The cookie belongs to another database than ODOO_DB. */
    status = 401;
    data = { ok: false, error: "Please sign in again." };
  }
  /* Odoo may keep the session id it was handed; a fresh one is still the new sign-in. */
  return { status, data: data || { ok: false }, session: m ? m[1] : started, location };
}

/* The cookie the browser holds. httpOnly, so page scripts cannot read it. */
export function sessionCookie(value, { remember } = {}) {
  return {
    name: SESSION_COOKIE, value,
    httpOnly: true, sameSite: "lax", path: "/",
    secure: process.env.NODE_ENV === "production",
    ...(remember ? { maxAge: 60 * 60 * 24 * 30 } : {}),
  };
}

/* Drops the cookie. Cleared with the same attributes it was set with, so no
   browser treats the clearing as a different cookie and keeps the old one. */
export function clearSessionCookie() {
  return { ...sessionCookie(""), maxAge: 0 };
}

/* Same call as odooFetch, but hands back the raw Response instead of parsed
   JSON. The invoice route needs it (that one answers application/pdf, and
   odooFetch's `await r.json()` would turn a perfectly good PDF into {ok:false}),
   and so do the picture passthroughs under app/web and app/369mart. */
export async function odooRaw(path, { method = "GET", session } = {}) {
  if (!ODOO_URL) return null; /* caller answers 503 */
  try {
    return await fetch(ODOO_URL + path, {
      method, headers: odooHeaders({ Accept: "*/*" }, session), cache: "no-store", redirect: "manual",
    });
  } catch (e) {
    return null; /* caller answers 503 */
  }
}

/* Product pictures and asset bundles: Odoo hands the shop short addresses like
   /web/image/product.template/13/image_512, which the browser asks this app
   for. The routes under app/web and app/369mart pass them through here, with
   ODOO_DB attached — something a next.config rewrite cannot do. Signed-out on
   purpose, as before: a picture never needs to know who is looking. */
const PASSED = ["content-type", "content-length", "content-disposition", "cache-control", "etag", "last-modified"];

export async function odooPassthrough(req, path) {
  if (!ODOO_URL) return new Response(NOT_CONNECTED, { status: 503 });
  const headers = odooHeaders({ Accept: req.headers.get("accept") || "*/*" });
  for (const h of ["if-none-match", "if-modified-since"]) {
    const v = req.headers.get(h);
    if (v) headers[h] = v;
  }
  let r;
  try {
    r = await fetch(ODOO_URL + path + new URL(req.url).search, { headers, cache: "no-store", redirect: "manual" });
  } catch (e) {
    return new Response(null, { status: 503 });
  }
  const out = new Headers();
  for (const h of PASSED) {
    const v = r.headers.get(h);
    if (v) out.set(h, v);
  }
  return new Response(r.status === 304 ? null : r.body, { status: r.status, headers: out });
}
