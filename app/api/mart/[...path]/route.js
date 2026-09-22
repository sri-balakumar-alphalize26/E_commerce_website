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

/* ---------------------------------------------------------------- last good

   When Odoo stops answering, the shop should show the last real answer it gave
   — not nothing, and certainly not something made up. This is the same trick a
   CDN does with stale-if-error, one hop closer.

   Only these feeds are kept. They are all auth='public' with save_session off,
   so every visitor gets a byte-identical body and there is nothing personal to
   leak by handing one visitor's copy to the next. Everything absent from this
   list — orders, wallet, payment, addresses, account, support — is never
   stored and never served from here. */
const KEEPABLE = new Set([
  "home", "catalog", "browse", "product", "search",
  "cart", "slots", "serviceability", "products", "offers",
]);
const LAST_GOOD = new Map(); /* url -> { body, at } */
const KEEP_MAX = 200;

function keepable(method, path) {
  if (method !== "GET" || !KEEPABLE.has(path[0])) return false;
  /* One exception inside an allowed prefix: a customer's own search history. */
  return !(path[0] === "search" && path[1] === "recent");
}

function remember(url, body) {
  if (LAST_GOOD.size >= KEEP_MAX && !LAST_GOOD.has(url)) {
    LAST_GOOD.delete(LAST_GOOD.keys().next().value); /* oldest out */
  }
  LAST_GOOD.set(url, { body, at: Date.now() });
}

async function handle(req, ctx) {
  const { path } = await ctx.params;
  if (badPath(path)) return NextResponse.json({ ok: false, error: "Unknown request." }, { status: 404 });

  const session = (await cookies()).get(SESSION_COOKIE)?.value;
  const target = "/369mart/" + path.join("/") + new URL(req.url).search;

  /* A few routes answer bytes rather than JSON: an invoice is a PDF, and a
     return's photos are images. `odooFetch` runs `await r.json()` over
     everything, which would turn a perfectly good file into {ok:false}, so
     these stream through untouched.

     Named rather than sniffed by content-type, because the decision has to be
     made before the body is read. Either of them can still answer JSON — an
     invoice that has not been posted, a photo that is not there — and that
     case is handed back to the app to read as usual. */
  if (path.includes("invoice") || path.includes("photo")) {
    const r = await odooRaw(target, { session });
    if (!r) return NextResponse.json({ ok: false, error: "Can't reach the store. Try again in a moment." }, { status: 503 });
    const type = r.headers.get("content-type") || "application/octet-stream";
    if (type.includes("json") || type.includes("html")) {
      /* Odoo answered about the file rather than with it. Let the app read it.
         `location` matters: a signed-out request is a 303 to /web/login, and
         without it that reads as 502 "the store broke" instead of 401 "sign in
         again", which is the one status the app acts on. */
      return NextResponse.json(
        await r.json().catch(() => ({ ok: false })),
        { status: outward(r.status, r.headers.get("location") || "") });
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
  const keep = keepable(method, path);

  /* Odoo could not answer at all. Hand back the last thing it did say, rather
     than let the shop fall back to something invented. Only 502 and 503 count:
     a 404 is a real answer and has to reach the app, or a product page loses
     its ability to say the product is not there. */
  if ((out === 502 || out === 503) && keep) {
    const held = LAST_GOOD.get(target);
    if (held) {
      const res = NextResponse.json(held.body, { status: 200 });
      res.headers.set("Cache-Control", "no-store");
      res.headers.set("x-mart-stale-age", String(Math.round((Date.now() - held.at) / 1000)));
      return res;
    }
  }

  if (out >= 200 && out < 300 && keep) remember(target, data);

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
