import { NextResponse } from "next/server";
import { clientIp, odooFetch, sessionCookie } from "@/lib/odoo";

export async function POST(req) {
  const { login, password, remember } = await req.json().catch(() => ({}));
  /* The visitor's address and browser go along: a staff member signing in
     here is reported to the Owner (mart369_auth `_mart369_on_staff_sign_in`). */
  const { status, data, session } = await odooFetch("/369mart/auth/login", {
    method: "POST", body: { login, password }, fresh: true,
    forwardFor: clientIp(req), device: req.headers.get("user-agent"),
  });
  const res = NextResponse.json(data, { status: status >= 500 ? 502 : status });
  if (data?.ok && session) res.cookies.set(sessionCookie(session, { remember: !!remember }));
  return res;
}
