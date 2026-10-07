import { NextResponse } from "next/server";
import { SESSION_COOKIE } from "@/lib/odoo";

/* Pages that need an account. The cookie's presence gates the page; /api/auth/me
   validates it against Odoo once the page loads. */
export function middleware(req) {
  if (req.cookies.get(SESSION_COOKIE)) return NextResponse.next();
  const target = "/login?next=" + encodeURIComponent(req.nextUrl.pathname + req.nextUrl.search);
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
    `<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="0;url=${href}">` +
    `<script>location.replace(${JSON.stringify(target)})</script>` +
    `<a href="${href}">Sign in to continue</a>`,
    { status: 200, headers: { "content-type": "text/html; charset=utf-8", "cache-control": "no-store" } },
  );
}

export const config = { matcher: ["/account/:path*", "/admin/:path*", "/checkout", "/order/:path*", "/track/:path*"] };
