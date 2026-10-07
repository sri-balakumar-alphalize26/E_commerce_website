import { NextResponse } from "next/server";
import { clientIp, odooFetch } from "@/lib/odoo";

/* A staff member's sign-in code on WhatsApp. Odoo answers the same for a
   number that is nobody's on the staff, so the page can't be used to probe. */
export async function POST(req) {
  const body = await req.json().catch(() => ({}));
  const { status, data } = await odooFetch("/369mart/auth/staff/phone/start", {
    method: "POST", body, forwardFor: clientIp(req),
  });
  return NextResponse.json(data, { status: status >= 500 && status !== 503 ? 502 : status });
}
