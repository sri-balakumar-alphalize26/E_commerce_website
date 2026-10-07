"use client";
/* ==========================================================================
   The staff console's own sign-in (the console's address + /login).

   Split: the brand panel on the left says whose door this is; the card on the
   right signs in, two ways -
     Mobile  number -> code on WhatsApp -> the account's password
     Email   email or username -> password
   Both land in the console's own cookie (mart_admin_session), never the
   customer's. Wrong details say so in plain words; a customer's details are
   refused ("This is not a staff account").

   The console's address is read from where this page is (its first path
   segment), so the secret address set on the server is never written here.
   ========================================================================== */
import "./staff-signin.css";
import { useEffect, useRef, useState } from "react";
import { PhoneInput } from "@/components/signin/SignIn";

const post = async (path, body) => {
  try {
    const r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const data = await r.json().catch(() => ({}));
    return { status: r.status, ...data };
  } catch (e) {
    return { ok: false, error: "Can't reach the server. Try again." };
  }
};

/* "/staff-k7p2x9" from "/staff-k7p2x9/login". */
const consoleBase = () => "/" + (window.location.pathname.split("/")[1] || "admin");

export default function StaffSignIn() {
  const [tab, setTab] = useState("mobile");
  const [countries, setCountries] = useState([]);
  const [country, setCountry] = useState("");
  const [home, setHome] = useState("");
  const [phone, setPhone] = useState("");
  const [step, setStep] = useState("number"); /* number | code | password */
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [login, setLogin] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState({ field: "", msg: "" });
  const [notice, setNotice] = useState("");
  const codeRef = useRef(null);
  const pwRef = useRef(null);

  useEffect(() => {
    fetch("/api/auth/phone-form").then((r) => r.json()).then((r) => {
      setCountries(r.countries || []);
      setCountry((c) => c || r.country?.code || "");
      setHome(r.country?.code || "");
    }).catch(() => {});
  }, []);
  useEffect(() => { if (step === "code") codeRef.current?.focus(); if (step === "password") pwRef.current?.focus(); }, [step]);

  const fail = (r, fallback) => setError({ field: r.field || "", msg: r.error || fallback });
  const done = () => {
    const base = consoleBase();
    const next = new URLSearchParams(window.location.search).get("next") || "";
    const safe = next.startsWith(base + "/") || next === base;
    window.location.replace(safe && !next.startsWith(base + "/login") ? next : base);
  };
  const switchTab = (t) => { setTab(t); setError({ field: "", msg: "" }); setNotice(""); setStep("number"); setCode(""); setPassword(""); };

  const sendCode = async (e) => {
    e?.preventDefault();
    if (busy) return;
    setBusy(true); setError({ field: "", msg: "" });
    const r = await post("/api/admin/phone/start", { phone, country });
    setBusy(false);
    if (!r.ok) return fail(r, "Couldn't send a code.");
    setNotice(r.message || "If this number is a staff member's, a code is on its way to WhatsApp.");
    setCode(""); setStep("code");
  };

  const checkCode = async (e) => {
    e?.preventDefault();
    if (busy || code.length !== 6) return;
    setBusy(true); setError({ field: "", msg: "" });
    const r = await post("/api/admin/phone/verify", { phone, country, code });
    setBusy(false);
    if (r.needPassword) { setNotice("Code accepted. Now your password."); setStep("password"); return; }
    if (r.ok) return done();
    fail(r, "That code is not right.");
  };

  const finishMobile = async (e) => {
    e.preventDefault();
    if (busy || !password) return;
    setBusy(true); setError({ field: "", msg: "" });
    const r = await post("/api/admin/phone/verify", { phone, country, code, password });
    setBusy(false);
    if (r.ok) return done();
    if (r.field === "code") { setStep("code"); setCode(""); }
    fail(r, "That password is not right.");
  };

  const signInEmail = async (e) => {
    e.preventDefault();
    if (busy || !login || !password) return;
    setBusy(true); setError({ field: "", msg: "" });
    const r = await post("/api/admin/login", { login, password });
    setBusy(false);
    if (r.ok) return done();
    fail(r, r.status === 401 ? "Wrong email/username or password." : "Couldn't sign in. Try again.");
  };

  const err = error.msg && <p className="ss-err" role="alert">{error.msg}</p>;

  return (
    <div className="ss-page">
      <aside className="ss-brand" aria-label="369 Mart staff console">
        <span className="ss-logo"><img src="/brand/369mart-logo.png" alt="369 Mart" width="166" height="88" /></span>
        <p className="ss-eyebrow">Staff console</p>
        <h1>Run the shop from one place.</h1>
        <ul className="ss-perks">
          <li><span aria-hidden="true">📦</span>Orders, the counter and returns</li>
          <li><span aria-hidden="true">🛵</span>Riders and live delivery</li>
          <li><span aria-hidden="true">🗂️</span>Catalogue and the home page</li>
          <li><span aria-hidden="true">👥</span>Staff, roles and settings</li>
        </ul>
        <p className="ss-trust"><span aria-hidden="true">🔒</span>Staff only. Every sign-in is logged and the Owner is told on WhatsApp.</p>
      </aside>

      <main className="ss-main">
        <section className="ss-card" aria-labelledby="ss-title">
          <h2 id="ss-title">Staff sign in</h2>
          <div className="ss-tabs" role="tablist" aria-label="How to sign in">
            {[["mobile", "Mobile"], ["email", "Email or username"]].map(([k, l]) => (
              <button key={k} type="button" role="tab" aria-selected={tab === k}
                className={tab === k ? "ss-on" : ""} onClick={() => switchTab(k)}>{l}</button>
            ))}
          </div>

          {tab === "mobile" && step === "number" && (
            <form className="ss-form" onSubmit={sendCode}>
              <label htmlFor="ss-phone">Mobile number</label>
              <PhoneInput id="ss-phone" countries={countries.length ? countries : [{ code: country, dial: "" }]}
                country={country} home={home} onCountry={setCountry} value={phone} onChange={setPhone}
                invalid={error.field === "phone"} placeholder="Your mobile" autoFocus />
              {err}
              <button className="ss-primary" disabled={busy || phone.replace(/\D/g, "").length < 6}>
                {busy ? "Sending…" : "Send code on WhatsApp"}
              </button>
            </form>
          )}

          {tab === "mobile" && step === "code" && (
            <form className="ss-form" onSubmit={checkCode}>
              {notice && <p className="ss-note">{notice}</p>}
              <label htmlFor="ss-code">6-digit code</label>
              <input ref={codeRef} id="ss-code" className="ss-input ss-code" inputMode="numeric" autoComplete="one-time-code"
                maxLength={6} value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))} />
              {err}
              <button className="ss-primary" disabled={busy || code.length !== 6}>{busy ? "Checking…" : "Continue"}</button>
              <button type="button" className="ss-link" onClick={() => { setStep("number"); setError({ field: "", msg: "" }); }}>Use another number</button>
            </form>
          )}

          {tab === "mobile" && step === "password" && (
            <form className="ss-form" onSubmit={finishMobile}>
              {notice && <p className="ss-note">{notice}</p>}
              <label htmlFor="ss-pw">Password</label>
              <input ref={pwRef} id="ss-pw" type="password" className="ss-input" autoComplete="current-password"
                value={password} onChange={(e) => setPassword(e.target.value)} />
              {err}
              <button className="ss-primary" disabled={busy || !password}>{busy ? "Signing in…" : "Sign in"}</button>
            </form>
          )}

          {tab === "email" && (
            <form className="ss-form" onSubmit={signInEmail}>
              <label htmlFor="ss-login">Email or username</label>
              <input id="ss-login" className="ss-input" autoComplete="username" autoFocus
                value={login} onChange={(e) => setLogin(e.target.value)} />
              <label htmlFor="ss-pw2">Password</label>
              <input id="ss-pw2" type="password" className="ss-input" autoComplete="current-password"
                value={password} onChange={(e) => setPassword(e.target.value)} />
              {err}
              <button className="ss-primary" disabled={busy || !login || !password}>{busy ? "Signing in…" : "Sign in"}</button>
            </form>
          )}

          <a className="ss-back" href="/">← Back to the store</a>
        </section>
      </main>
    </div>
  );
}
