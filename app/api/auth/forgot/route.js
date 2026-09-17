import { NextResponse } from "next/server";
import { odooFetch } from "@/lib/odoo";

export async function POST(req) {
  const { email } = await req.json().catch(() => ({}));
  await odooFetch("/369mart/auth/forgot", { method: "POST", body: { email } });
  /* Never say whether the email has an account. */
  return NextResponse.json({ ok: true });
}
