import { NextResponse } from "next/server";
import { adminCookie, clientIp, odooFetch } from "@/lib/odoo";

/* Staff sign-in with email or username + password, into the console's own
   cookie. A customer's details are refused - and the Odoo session they just
   opened is closed again - so this page never hands a customer a session. */
export async function POST(req) {
  const { login, password } = await req.json().catch(() => ({}));
  const { status, data, session } = await odooFetch("/369mart/auth/login", {
    method: "POST", body: { login, password }, fresh: true, forwardFor: clientIp(req), device: req.headers.get("user-agent"),
  });
  if (!data?.ok || !session) {
    return NextResponse.json(data?.ok ? { ok: false, error: "Can't sign in right now." } : data,
      { status: status >= 500 ? 502 : status === 200 ? 401 : status });
  }
  if (!data.staff) {
    await odooFetch("/369mart/auth/logout", { method: "POST", body: {}, session });
    return NextResponse.json({ ok: false, error: "This is not a staff account.", field: "login" }, { status: 403 });
  }
  const res = NextResponse.json(data);
  res.cookies.set(adminCookie(session));
  return res;
}
