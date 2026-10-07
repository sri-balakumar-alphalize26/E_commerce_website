import { NextResponse } from "next/server";
import { cookies } from "next/headers";
import { clientIp, odooFetch, SESSION_COOKIE } from "@/lib/odoo";

/* A signed-in account with no proven number asks for a code to add one. */
export async function POST(req) {
  const session = (await cookies()).get(SESSION_COOKIE)?.value;
  if (!session) return NextResponse.json({ ok: false, error: "Please sign in again." }, { status: 401 });
  const body = await req.json().catch(() => ({}));
  const { status, data } = await odooFetch("/369mart/auth/phone/add-start", {
    method: "POST", body, session, forwardFor: clientIp(req),
  });
  return NextResponse.json(data, { status: status >= 300 && status < 400 ? 401 : status });
}
