import { NextResponse } from "next/server";
import { cookies } from "next/headers";
import { ADMIN_COOKIE, clearAdminCookie, odooFetch } from "@/lib/odoo";

/* Signs the console out. The customer's own sign-in, if any, is untouched. */
export async function POST() {
  const session = (await cookies()).get(ADMIN_COOKIE)?.value;
  if (session) await odooFetch("/369mart/auth/logout", { method: "POST", body: {}, session });
  const res = NextResponse.json({ ok: true });
  res.cookies.set(clearAdminCookie());
  return res;
}
