"use client";
/* ==========================================================================
   Who may open the admin console.

   The console has its own sign-in (mart_admin_session, /admin/login) beside
   the customer's, so one browser can be both. middleware.js only checks that
   the console's cookie is there; this is the real check: it asks
   /api/admin/me who the cookie belongs to, and opens the console only for
   staff. `staff` is the same group every /369mart/admin/* route checks
   (website.group_website_designer), so the gate and the data cannot disagree.

   - <console>/login     -> the sign-in page itself, never gated
   - still asking        -> a quiet "checking" screen, never the console
   - nobody / stale      -> <console>/login?next=<here>  (the me route drops the cookie)
   - not staff (any more)-> "this area is for staff", with a way out
   - staff               -> the console, told who is signed in (useAdminMe)
   ========================================================================== */
import { createContext, useContext, useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { consolePath } from "@/lib/consolePath";

const AdminMe = createContext(null);

/* The signed-in staff member: {name, email, ...}. Null outside the gate. */
export const useAdminMe = () => useContext(AdminMe);

/* Signs the console out - the customer's own sign-in, if any, stays - and
   back to the staff sign-in. */
export async function signOut() {
  try { await fetch("/api/admin/logout", { method: "POST" }); } catch (e) { /* the cookie is cleared either way */ }
  window.location.assign(consolePath("/login"));
}

export default function AdminGate({ children }) {
  const path = usePathname();
  /* "<console>/login" - /admin/login, or the secret address + /login. */
  const open = /^\/[^/]+\/login\/?$/.test(path || "");
  const [state, setState] = useState({ phase: "checking", me: null });

  /* Every request from here rides the console's sign-in (lib/api.js reads
     this flag), whatever the console's address is. */
  useEffect(() => {
    document.documentElement.dataset.console = "1";
    return () => { delete document.documentElement.dataset.console; };
  }, []);

  useEffect(() => {
    if (open) return undefined;
    let alive = true;
    (async () => {
      let me = null;
      let down = false;
      try {
        const r = await fetch("/api/admin/me", { cache: "no-store" });
        down = r.status === 503;
        if (r.ok) me = await r.json();
      } catch (e) { down = true; }
      if (!alive) return;
      if (down) { setState({ phase: "down", me: null }); return; }
      if (!me?.ok) {
        const here = window.location.pathname + window.location.search;
        window.location.replace(consolePath("/login") + "?next=" + encodeURIComponent(here));
        return;
      }
      setState({ phase: me.staff ? "staff" : "customer", me });
    })();
    return () => { alive = false; };
  }, [open]);

  if (open) return children;

  if (state.phase === "staff") {
    return <AdminMe.Provider value={state.me}>{children}</AdminMe.Provider>;
  }

  return (
    <div className="ad-gate">
      {state.phase === "customer" ? (
        <div className="ad-gate-card">
          <b>This area is for 369 Mart staff</b>
          <p>
            {state.me.name}{state.me.email ? ` (${state.me.email})` : ""} is not a staff account any more.
            Sign in with a staff account to open the console.
          </p>
          <div className="ad-gate-act">
            <a className="ad-btn" href="/">Go to the store</a>
            <button className="ad-btn ad-primary" onClick={signOut}>Sign out</button>
          </div>
        </div>
      ) : state.phase === "down" ? (
        <div className="ad-gate-card">
          <b>Can't reach the store</b>
          <p>The shop's server isn't answering. Try again in a moment.</p>
          <div className="ad-gate-act"><button className="ad-btn ad-primary" onClick={() => window.location.reload()}>Try again</button></div>
        </div>
      ) : (
        <p className="ad-gate-wait">Checking your account…</p>
      )}
    </div>
  );
}
