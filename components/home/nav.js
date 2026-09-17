"use client";
/* In-app navigation shared by every view.
   nav(view, param?, { replace?, keepScroll? })
     nav("home")                              → /
     nav("category", "staples/oils-ghee")     → /category/staples/oils-ghee
     nav("search", "atta")                    → /search?q=atta
     nav("offers") · nav("buyagain")          → /offers · /buy-again
     nav("product", "d2") · nav("cart") · nav("account")
     nav("checkout") · nav("order", "369M-…")           → /checkout · /order/<id> */
import { createContext } from "react";

export const NavContext = createContext(() => {});

export function routeToPath(view, param) {
  switch (view) {
    case "home": return "/";
    case "category": return "/category/" + String(param || "").split("/").map(encodeURIComponent).join("/");
    case "search": return "/search?q=" + encodeURIComponent(param || "");
    case "offers": return "/offers";
    case "buyagain": return "/buy-again";
    case "product": return "/product/" + encodeURIComponent(param || "");
    case "cart": return "/cart";
    case "account": return "/account";
    case "checkout": return "/checkout";
    case "order": return "/order/" + encodeURIComponent(param || "");
    case "track": return "/track/" + encodeURIComponent(param || "");
    default: return "/";
  }
}

export function pathToRoute(pathname, search = "") {
  const parts = pathname.split("/").filter(Boolean).map((s) => decodeURIComponent(s));
  const [head, ...rest] = parts;
  if (!head) return { view: "home", param: null };
  if (head === "category") return { view: "category", param: rest.join("/") };
  if (head === "search") return { view: "search", param: new URLSearchParams(search).get("q") || "" };
  if (head === "offers") return { view: "offers", param: null };
  if (head === "buy-again") return { view: "buyagain", param: null };
  if (head === "product") return { view: "product", param: rest[0] || "" };
  if (head === "cart") return { view: "cart", param: null };
  if (head === "account") return { view: "account", param: null };
  if (head === "checkout") return { view: "checkout", param: null };
  if (head === "order") return { view: "order", param: rest[0] || "" };
  if (head === "track") return { view: "track", param: rest[0] || "" };
  return { view: "notfound", param: null };
}
