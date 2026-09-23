"use client";
/* ==========================================================================
   Who may open the admin console.

   middleware.js only checks that a session cookie is there - any customer,
   and any stale or made-up cookie, gets past it. This is the real check: it
   asks /api/auth/me who the cookie belongs to, and opens the console only for
   staff. `staff` is the same group every /369mart/admin/* route checks
   (website.group_website_designer), so the gate and the data cannot disagree.

   - still asking        -> a quiet "checking" screen, never the console
   - nobody / stale      -> /login?next=<here>  (the me route drops the cookie)
   - a customer          -> "this area is for staff", with a way out
   - staff               -> the console, told who is signed in (useAdminMe)
   ========================================================================== */
import { createContext, useContext, useEffect, useState } from "react";

const AdminMe = createContext(null);

/* The signed-in staff member: {name, email, ...}. Null outside the gate. */
export const useAdminMe = () => useContext(AdminMe);

/* The same sign-out the storefront uses, then back to the login page. */
export async function signOut() {
  try { await fetch("/api/auth/logout", { method: "POST" }); } catch (e) { /* the cookie is cleared either way */ }
  window.location.assign("/login");
}

export default function AdminGate({ children }) {
  const [state, setState] = useState({ phase: "checking", me: null });

  useEffect(() => {
    let alive = true;
    (async () => {
      let me = null;
      try {
        const r = await fetch("/api/auth/me", { cache: "no-store" });
        if (r.ok) me = await r.json();
      } catch (e) { /* treated as signed out */ }
      if (!alive) return;
      if (!me?.ok) {
        const here = window.location.pathname + window.location.search;
        window.location.replace("/login?next=" + encodeURIComponent(here));
        return;
      }
      setState({ phase: me.staff ? "staff" : "customer", me });
    })();
    return () => { alive = false; };
  }, []);

  if (state.phase === "staff") {
    return <AdminMe.Provider value={state.me}>{children}</AdminMe.Provider>;
  }

  return (
    <div className="ad-gate">
      {state.phase === "customer" ? (
        <div className="ad-gate-card">
          <b>This area is for 369 Mart staff</b>
          <p>
            You are signed in as {state.me.name}{state.me.email ? ` (${state.me.email})` : ""}, which is a
            customer account. Sign in with a staff account to open the console.
          </p>
          <div className="ad-gate-act">
            <a className="ad-btn" href="/">Go to the store</a>
            <button className="ad-btn ad-primary" onClick={signOut}>Sign out</button>
          </div>
        </div>
      ) : (
        <p className="ad-gate-wait">Checking your account…</p>
      )}
    </div>
  );
}
