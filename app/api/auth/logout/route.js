import { NextResponse } from "next/server";
import { cookies } from "next/headers";
import { clearSessionCookie, odooFetch, SESSION_COOKIE } from "@/lib/odoo";

export async function POST() {
  const session = (await cookies()).get(SESSION_COOKIE)?.value;
  if (session) await odooFetch("/369mart/auth/logout", { method: "POST", body: {}, session });
  const res = NextResponse.json({ ok: true });
  res.cookies.set(clearSessionCookie());
  return res;
}
