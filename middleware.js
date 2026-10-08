import { NextResponse } from "next/server";
import { ADMIN_COOKIE, SESSION_COOKIE } from "@/lib/odoo";

/* Pages that need an account. The cookie's presence gates the page; the
   page's own "who am I" call (/api/auth/me, or /api/admin/me in the console)
   validates it against Odoo once it loads.

   Two doors: the shop's pages need the customer's sign-in and go to /login;
   the staff console needs its own sign-in and goes to <console>/login, the one
   console page anyone may open.

   **The console's address.** With ADMIN_PATH set in .env.local (a word only
   staff know, e.g. staff-k7p2x9) the console answers there and /admin is
   "page not found" - bots trying /admin on every site never see a sign-in
   page. The pages still live under app/admin; the secret address is rewritten
   onto them here. Without ADMIN_PATH the console stays at /admin (local dev).
   Change the word, rebuild and restart: the old address stops at once. */
const SECRET = (process.env.ADMIN_PATH || "").trim().replace(/^\/+|\/+$/g, "");
const HIDDEN = Boolean(SECRET) && SECRET !== "admin";
const CONSOLE = HIDDEN ? SECRET : "admin";
const CUSTOMER = ["/account", "/checkout", "/order/", "/track/"];

export function middleware(req) {
  const path = req.nextUrl.pathname;
  const first = path.split("/")[1] || "";

  if (first === CONSOLE || first === "admin") {
    if (HIDDEN && first === "admin") {
      /* Not here. Rendered by app/not-found.jsx with a 404, like any page that isn't. */
      const url = req.nextUrl.clone();
      url.pathname = "/_not-found-console";
      return NextResponse.rewrite(url);
    }
    const rest = path.slice(first.length + 1);            // "", "/orders", "/login"
    const login = rest === "/login" || rest === "/login/";
    if (!login && !req.cookies.get(ADMIN_COOKIE)) return toSignIn(req, `/${CONSOLE}/login`);
    const res = HIDDEN
      ? NextResponse.rewrite(Object.assign(req.nextUrl.clone(), { pathname: "/admin" + rest }))
      : NextResponse.next();
    /* Never in a search engine. Not listed in robots.txt either, which would
       publish the secret address. */
    res.headers.set("X-Robots-Tag", "noindex, nofollow");
    return res;
  }

  if (CUSTOMER.some((p) => path === p.replace(/\/$/, "") || path.startsWith(p))) {
    if (req.cookies.get(SESSION_COOKIE)) return NextResponse.next();
    return toSignIn(req, "/login");
  }
  return NextResponse.next();
}

function toSignIn(req, page) {
  const target = page + "?next=" + encodeURIComponent(req.nextUrl.pathname + req.nextUrl.search);
  /* Never req.nextUrl's own host: behind the live server's proxy that is the
     app's internal address (https://localhost:3002/...), and a visitor sent
     there gets a page that never opens. A proxy that says which address the
     visitor used gets a normal redirect to it; one that doesn't gets a page
     that moves the browser on by itself - a relative address, resolved
     against wherever the visitor really is. (Middleware refuses a relative
     Location header outright.) */
  /* Next fills x-forwarded-host from the Host header when the proxy sends
     none, so a proxy passing Host: localhost:3002 (as the live one does)
     arrives here as that - treated as "not known". */
  const host = req.headers.get("x-forwarded-host");
  if (host && !/^(localhost|127\.|\[?::1)/i.test(host.trim())) {
    const proto = (req.headers.get("x-forwarded-proto") || "https").split(",")[0].trim();
    return NextResponse.redirect(`${proto}://${host.split(",")[0].trim()}${target}`, 307);
  }
  const href = target.replace(/&/g, "&amp;").replace(/"/g, "&quot;");
  return new NextResponse(
    `<!doctype html><meta charset="utf-8"><meta name="robots" content="noindex"><meta http-equiv="refresh" content="0;url=${href}">` +
    `<script>location.replace(${JSON.stringify(target)})</script>` +
    `<a href="${href}">Sign in to continue</a>`,
    { status: 200, headers: { "content-type": "text/html; charset=utf-8", "cache-control": "no-store" } },
  );
}

/* Every page path (the console's address can be any word), but never the
   app's own files, images or API routes. */
export const config = { matcher: ["/((?!_next/|api/|web/|369mart/|brand/|fonts/|images/|sw\\.js|favicon|icon|robots).*)"] };
