import { NextResponse } from "next/server";
import { clientIp, odooFetch, sessionCookie } from "@/lib/odoo";

/* The code (and, once, the password of an account whose number was never
   proven) signs the customer in. Kept like a "remember me" sign-in. */
export async function POST(req) {
  const body = await req.json().catch(() => ({}));
  const { status, data, session } = await odooFetch("/369mart/auth/phone/verify", {
    method: "POST", body, fresh: true, forwardFor: clientIp(req),
  });
  const res = NextResponse.json(data, { status: status >= 500 ? 502 : status });
  if (data?.ok && session) res.cookies.set(sessionCookie(session, { remember: true }));
  return res;
}
