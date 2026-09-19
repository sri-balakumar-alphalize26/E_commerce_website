/* Server-side only: the storefront's route handlers talk to Odoo through this.
   The browser never sees ODOO_URL or Odoo's session cookie. */

const ODOO_URL = (process.env.ODOO_URL || "http://localhost:8097").replace(/\/$/, "");
export const SESSION_COOKIE = "mart_session";

export async function odooFetch(path, { method = "GET", body, session } = {}) {
  const headers = { "Content-Type": "application/json", Accept: "application/json" };
  if (session) headers.Cookie = `session_id=${session}`;
  let r;
  try {
    r = await fetch(ODOO_URL + path, {
      method, headers, body: body ? JSON.stringify(body) : undefined,
      cache: "no-store", redirect: "manual",
    });
  } catch (e) {
    return { status: 503, data: { ok: false, error: "Can't reach the account server. Try again in a moment." }, session: null };
  }
  const m = (r.headers.get("set-cookie") || "").match(/session_id=([^;]+)/);
  const location = r.headers.get("location") || "";
  let data = null;
  try { data = await r.json(); } catch (e) {}
  if (r.status >= 300 && r.status < 400) {
    /* Two very different things arrive as a redirect. A route that needs a
       signed-in customer answers 303 to /web/login when the session is missing
       or stale — that is simply "signed out". Anything else means Odoo did not
       know which database to use. Callers tell them apart with `location`. */
    data = /\/web\/login/.test(location)
      ? { ok: false, error: "Please sign in again." }
      : { ok: false, error: "The account server is not configured for this store." };
  }
  return { status: r.status, data: data || { ok: false }, session: m ? m[1] : null, location };
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

/* Same call as odooFetch, but hands back the raw Response instead of parsed
   JSON. Only the invoice route needs it: that one answers application/pdf, and
   odooFetch's `await r.json()` would turn a perfectly good PDF into {ok:false}. */
export async function odooRaw(path, { method = "GET", session } = {}) {
  const headers = { Accept: "*/*" };
  if (session) headers.Cookie = `session_id=${session}`;
  try {
    return await fetch(ODOO_URL + path, { method, headers, cache: "no-store", redirect: "manual" });
  } catch (e) {
    return null; /* caller answers 503 */
  }
}
