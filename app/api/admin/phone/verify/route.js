import { NextResponse } from "next/server";
import { adminCookie, clientIp, odooFetch } from "@/lib/odoo";

/* The code, then the password: both pass, or no console session. */
export async function POST(req) {
  const body = await req.json().catch(() => ({}));
  const { status, data, session } = await odooFetch("/369mart/auth/staff/phone/verify", {
    method: "POST", body, fresh: true, forwardFor: clientIp(req), device: req.headers.get("user-agent"),
  });
  const res = NextResponse.json(data, { status: status >= 500 ? 502 : status });
  if (data?.ok && session) res.cookies.set(adminCookie(session));
  return res;
}
