import { NextResponse } from "next/server";
import { cookies } from "next/headers";
import { ADMIN_COOKIE, clearAdminCookie, odooFetch } from "@/lib/odoo";

/* Who the console's cookie belongs to. 401 when there is none or Odoo no
   longer accepts it (the cookie is dropped); 503 when Odoo can't be reached
   (the cookie is kept). `staff: false` reaches the gate, which says so. */
export async function GET() {
  const session = (await cookies()).get(ADMIN_COOKIE)?.value;
  if (!session) return NextResponse.json({ ok: false }, { status: 401 });
  const { status, data } = await odooFetch("/369mart/auth/me", { session });
  if (status >= 500) return NextResponse.json({ ok: false, error: data?.error || "Can't reach the store." }, { status: 503 });
  if (status !== 200 || !data?.ok) {
    const res = NextResponse.json({ ok: false }, { status: 401 });
    res.cookies.set(clearAdminCookie());
    return res;
  }
  return NextResponse.json(data);
}
