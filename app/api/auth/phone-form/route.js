import { NextResponse } from "next/server";
import { odooFetch } from "@/lib/odoo";

/* The country picker's data before anyone is signed in: the default country
   is the company's, from the database - never a hard-coded +91. */
export async function GET(req) {
  const country = new URL(req.url).searchParams.get("country") || "";
  const q = country ? `?country=${encodeURIComponent(country)}` : "";
  const { status, data } = await odooFetch(`/369mart/auth/phone-form${q}`);
  return NextResponse.json(data, { status: status >= 500 ? 502 : status });
}
