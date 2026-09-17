import { NextResponse } from "next/server";
import { odooFetch, sessionCookie } from "@/lib/odoo";

export async function POST(req) {
  const { login, password, remember } = await req.json().catch(() => ({}));
  const { status, data, session } = await odooFetch("/369mart/auth/login", { method: "POST", body: { login, password } });
  const res = NextResponse.json(data, { status: status >= 500 ? 502 : status });
  if (data?.ok && session) res.cookies.set(sessionCookie(session, { remember: !!remember }));
  return res;
}
