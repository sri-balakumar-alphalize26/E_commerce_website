/* The one door between the browser and Odoo.

   /api/mart/<anything>  ->  <ODOO_URL>/369mart/<anything>

   Everything the storefront reads or writes goes through here, so the browser
   only ever calls its own origin: no CORS, no preflight, and no way for a page
   script to learn where Odoo lives. The session cookie is httpOnly, so this is
   also the only place that can turn it into Odoo's `session_id`.

   Auth is the exception: /api/auth/* keeps its own handlers because those set
   and clear the cookie, which a generic proxy has no business doing. */

import { NextResponse } from "next/server";
import { cookies } from "next/headers";
import { odooFetch, odooRaw, sessionCookie, SESSION_COOKIE } from "@/lib/odoo";

export const dynamic = "force-dynamic";

function badPath(parts) {
  return (
    !parts?.length ||
    parts.length > 6 ||
    parts.some((s) => !s || s === "." || s === "..") ||
    parts[0] === "auth" /* must go through the cookie-setting handlers */
  );
}

/* Odoo's own status codes are the contract the app reads: 401 means signed
   out, 404 means not yours or not there, 409 means the state moved. They pass
   through untouched. Only the ones the app can do nothing with are rewritten.

   The redirect case matters most. A route needing a signed-in customer answers
   303 to /web/login, never 401 — so without this the app would read "signed
   out" as a server fault and never send anyone to sign in. */
function outward(status, location = "") {
  if (status >= 300 && status < 400) return /\/web\/login/.test(location) ? 401 : 502;
  if (status === 503) return 503; /* can't reach the store — distinct from a failure */
  if (status >= 500) return 502;
  return status;
}

async function handle(req, ctx) {
  const { path } = await ctx.params;
  if (badPath(path)) return NextResponse.json({ ok: false, error: "Unknown request." }, { status: 404 });

  const session = (await cookies()).get(SESSION_COOKIE)?.value;
  const target = "/369mart/" + path.join("/") + new URL(req.url).search;

  /* The invoice is a PDF, not JSON. Stream it through as-is. */
  if (path[path.length - 1] === "invoice") {
    const r = await odooRaw(target, { session });
    if (!r) return NextResponse.json({ ok: false, error: "Can't reach the store. Try again in a moment." }, { status: 503 });
    const type = r.headers.get("content-type") || "application/pdf";
    if (!type.includes("pdf")) {
      /* No invoice posted yet: Odoo answers JSON. Let the app read it. */
      return NextResponse.json(await r.json().catch(() => ({ ok: false })), { status: outward(r.status) });
    }
    return new Response(r.body, {
      status: r.status,
      headers: {
        "Content-Type": type,
        "Content-Disposition": r.headers.get("content-disposition") || "inline",
        "Cache-Control": "no-store",
      },
    });
  }

  const method = req.method;
  const body = method === "POST" || method === "PATCH" ? await req.json().catch(() => undefined) : undefined;
  const { status, data, session: rotated, location } = await odooFetch(target, { method, body, session });
  const out = outward(status, location);

  const res = NextResponse.json(data, { status: out });
  /* Never let a shared cache hold an answer that was fetched as this customer.
     The 60-second freshness Odoo asks for is done in lib/api.js instead. */
  res.headers.set("Cache-Control", "no-store");

  if (out === 401 && session) {
    /* The cookie is dead. Drop it, or middleware.js keeps waving it through. */
    res.cookies.set({ name: SESSION_COOKIE, value: "", path: "/", maxAge: 0 });
  } else if (rotated && rotated !== session) {
    res.cookies.set(sessionCookie(rotated, { remember: true }));
  }
  return res;
}

export const GET = handle;
export const POST = handle;
export const PATCH = handle;
export const DELETE = handle;
