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
  let data = null;
  try { data = await r.json(); } catch (e) {}
  if (r.status >= 300 && r.status < 400) {
    /* Odoo redirected — usually it does not know which database to use. */
    data = { ok: false, error: "The account server is not configured for this store." };
  }
  return { status: r.status, data: data || { ok: false }, session: m ? m[1] : null };
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
