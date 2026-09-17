import { NextResponse } from "next/server";
import { SESSION_COOKIE } from "@/lib/odoo";

/* Pages that need an account. The cookie's presence gates the page; /api/auth/me
   validates it against Odoo once the page loads. */
export function middleware(req) {
  if (req.cookies.get(SESSION_COOKIE)) return NextResponse.next();
  const url = req.nextUrl.clone();
  url.pathname = "/login";
  url.search = "?next=" + encodeURIComponent(req.nextUrl.pathname);
  return NextResponse.redirect(url);
}

export const config = { matcher: ["/account/:path*", "/checkout", "/order/:path*", "/track/:path*"] };
