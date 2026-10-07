import { NextResponse } from "next/server";
import { cookies } from "next/headers";
import { clearSessionCookie, odooFetch, SESSION_COOKIE } from "@/lib/odoo";

export async function GET() {
  const session = (await cookies()).get(SESSION_COOKIE)?.value;
  if (!session) return NextResponse.json({ ok: false }, { status: 401 });
  const { status, data } = await odooFetch("/369mart/auth/me", { session });
  /* The store not answering is not the customer being signed out: keep the
     cookie, so a restart of Odoo doesn't sign everybody out with it. */
  if (status >= 500) return NextResponse.json({ ok: false, error: data?.error || "Can't reach the store." }, { status: 503 });
  if (status !== 200 || !data?.ok) {
    const res = NextResponse.json({ ok: false }, { status: 401 });
    res.cookies.set(clearSessionCookie()); /* stale cookie: drop it */
    return res;
  }
  return NextResponse.json(data);
}
