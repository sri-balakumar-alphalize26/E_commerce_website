import { NextResponse } from "next/server";
import { odooFetch, sessionCookie } from "@/lib/odoo";

export async function POST(req) {
  const body = await req.json().catch(() => ({}));
  const { status, data, session } = await odooFetch("/369mart/auth/signup", { method: "POST", body });
  const res = NextResponse.json(data, { status: status >= 500 ? 502 : status });
  /* Kept like a "remember me" sign-in: somebody who has just made an account
     should not find themselves signed out the next time they open the browser. */
  if (data?.ok && session) res.cookies.set(sessionCookie(session, { remember: true }));
  return res;
}
