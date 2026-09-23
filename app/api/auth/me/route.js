import { NextResponse } from "next/server";
import { cookies } from "next/headers";
import { clearSessionCookie, odooFetch, SESSION_COOKIE } from "@/lib/odoo";

export async function GET() {
  const session = (await cookies()).get(SESSION_COOKIE)?.value;
  if (!session) return NextResponse.json({ ok: false }, { status: 401 });
  const { status, data } = await odooFetch("/369mart/auth/me", { session });
  if (status !== 200 || !data?.ok) {
    const res = NextResponse.json({ ok: false }, { status: 401 });
    res.cookies.set(clearSessionCookie()); /* stale cookie: drop it */
    return res;
  }
  return NextResponse.json(data);
}
