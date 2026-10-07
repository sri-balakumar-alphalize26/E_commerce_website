import { NextResponse } from "next/server";
import { clientIp, odooFetch } from "@/lib/odoo";

/* Send a sign-in (or sign-up) code to a mobile number's WhatsApp. Odoo's
   answer - including "no account, please sign up" and "codes are delayed" -
   passes straight through. */
export async function POST(req) {
  const body = await req.json().catch(() => ({}));
  const { status, data } = await odooFetch("/369mart/auth/phone/start", {
    method: "POST", body, forwardFor: clientIp(req),
  });
  return NextResponse.json(data, { status: status >= 500 && status !== 503 ? 502 : status });
}
