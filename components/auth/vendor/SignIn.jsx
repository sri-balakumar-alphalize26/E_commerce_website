"use client";
/* 369mart: this file is VENDORED from the 369mart_signin drop and carries one
   local edit, marked "369mart: LOCAL EDIT". Re-apply it on every update. */
/* ==========================================================================
   369 Mart — Sign in (email only)
   Sign in · Create account · Forgot password -> Check inbox · Done

   Drop-in for Next.js (App Router): app/login/page.jsx
     import SignInPage from "@/components/SignIn";
     import "@/components/signin.css";
     export default function Page() { return <SignInPage />; }

   Wire your backend through the props (all return Promises). Every prop has a
   demo default so the page works before the server is connected.
   ========================================================================== */
import { useEffect, useLayoutEffect, useRef, useState } from "react";

const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const demo = {
  emailSignIn: async (_email, password) => {
    await wait(900);
    if (password.length < 6) return { ok: false, error: "Email or password is incorrect." };
    return { ok: true, name: "" };
  },
  createAccount: async () => { await wait(1000); return { ok: true }; },
  forgotPassword: async () => { await wait(900); return { ok: true }; },
};
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;
/* 369mart: LOCAL EDIT -- re-apply after every drop of this file.

   The demo credential is deliberately not an email address, and this form
   checks the field itself before the app handler is ever called, so
   without this the demo sign-in could not be reached at all.

   Letting one exact literal through is narrower than loosening EMAIL_RE,
   which would weaken the check for every real customer. Create-account and
   forgot-password still reject it downstream, where they return a proper
   message instead of silently accepting it.

   Keep in step with DEMO_EMAIL in lib/session.ts. */
const DEMO_EMAIL = "abc";
const RESEND_SECONDS = 30;

function strength(pw) {
  let s = 0;
  if (pw.length >= 8) s++;
  if (/[a-z]/.test(pw) && /[A-Z]/.test(pw)) s++;
  if (/\d/.test(pw)) s++;
  if (/[^A-Za-z0-9]/.test(pw)) s++;
  return pw ? Math.max(1, s) : 0;
}
const STRENGTH = ["", "Weak", "Fair", "Good", "Strong"];

/* animates its own height when the step inside changes */
function Stage({ stepKey, dir, children }) {
  const outer = useRef(null);
  const inner = useRef(null);
  const [h, setH] = useState(null);
  useLayoutEffect(() => {
    if (!inner.current || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(() => setH(inner.current.offsetHeight));
    ro.observe(inner.current);
    return () => ro.disconnect();
  }, []);
  return (
    <div className="si-stage" ref={outer} style={h ? { height: h + 12 } : undefined}>
      <div ref={inner}>
        <div key={stepKey} className={"si-step " + (dir < 0 ? "si-back" : "si-fwd")}>{children}</div>
      </div>
    </div>
  );
}

function Spinner() {
  return <span className="si-spin" aria-hidden="true" />;
}

function Field({ id, label, error, hint, children, trailing }) {
  return (
    <div className={"si-field" + (error ? " si-invalid" : "")}>
      <div className="si-label-row"><label htmlFor={id}>{label}</label>{trailing}</div>
      {children}
      {error ? <p className="si-err" role="alert">{error}</p> : hint ? <p className="si-hint">{hint}</p> : null}
    </div>
  );
}

function PasswordInput({ id, value, onChange, autoComplete, shake, invalid, onCaps }) {
  const [show, setShow] = useState(false);
  return (
    <div className={"si-pw si-input" + (shake ? " si-shake" : "")}>
      <input id={id} type={show ? "text" : "password"} autoComplete={autoComplete} value={value}
        aria-invalid={invalid || undefined}
        onKeyUp={(e) => onCaps?.(e.getModifierState?.("CapsLock"))}
        onChange={(e) => onChange(e.target.value)} />
      <button type="button" className="si-eye" aria-label={show ? "Hide password" : "Show password"} aria-pressed={show} onClick={() => setShow((s) => !s)}>
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z" /><circle cx="12" cy="12" r="3" />
          <path className="si-eye-slash" d="M4 4l16 16" />
        </svg>
      </button>
    </div>
  );
}

const Check = () => (
  <span className="si-box" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M5 12.5l4.5 4.5L19 7.5" /></svg></span>
);
const BackIcon = () => <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M15 6l-6 6 6 6" /></svg>;

export function SignInCard({
  onEmailSignIn = demo.emailSignIn,
  onCreateAccount = demo.createAccount,
  onForgotPassword = demo.forgotPassword,
  onDone = () => {},
  onGuest,
  initialMode = "signin",
}) {
  const [mode, setMode] = useState(initialMode); // signin | create | forgot | sent | done
  const [dir, setDir] = useState(1);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState({ field: "", msg: "" });
  const [shakeKey, setShakeKey] = useState(0);

  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [caps, setCaps] = useState(false);
  const [remember, setRemember] = useState(true);
  const [agree, setAgree] = useState(true);
  const [left, setLeft] = useState(0);
  const [doneName, setDoneName] = useState("");

  const emailOk =
    email.trim().toLowerCase() === DEMO_EMAIL || EMAIL_RE.test(email.trim()); /* 369mart */
  const pwScore = strength(password);

  useEffect(() => {
    if (mode !== "sent" || left <= 0) return;
    const t = setTimeout(() => setLeft((s) => s - 1), 1000);
    return () => clearTimeout(t);
  }, [mode, left]);

  const go = (next, d = 1) => { setDir(d); setError({ field: "", msg: "" }); setPassword(""); setMode(next); };
  const fail = (field, msg) => { setError({ field, msg }); setShakeKey((k) => k + 1); };
  const clear = () => { if (error.msg) setError({ field: "", msg: "" }); };
  const errFor = (f) => (error.field === f ? error.msg : "");
  const shakeK = (f) => f + (error.field === f ? shakeKey : 0);

  async function submitSignIn(e) {
    e.preventDefault();
    if (!emailOk) return fail("email", "Enter a valid email address.");
    if (!password) return fail("password", "Enter your password.");
    setBusy(true);
    const r = await onEmailSignIn(email.trim(), password, remember);
    setBusy(false);
    if (!r?.ok) return fail("password", r?.error || "Email or password is incorrect.");
    setDoneName(r.name || ""); go("done");
  }

  async function submitCreate(e) {
    e.preventDefault();
    if (name.trim().length < 2) return fail("name", "Enter your name as it should appear on deliveries.");
    if (!emailOk) return fail("email", "Enter a valid email address.");
    if (password.length < 8) return fail("password", "Use at least 8 characters.");
    if (!agree) return fail("agree", "Accept the Terms to create an account.");
    setBusy(true);
    const r = await onCreateAccount({ name: name.trim(), email: email.trim(), password });
    setBusy(false);
    if (!r?.ok) return fail(r?.field || "email", r?.error || "Couldn't create the account. Try again.");
    setDoneName(name.trim()); go("done");
  }

  async function submitForgot(e) {
    e?.preventDefault();
    if (!emailOk) return fail("email", "Enter the email you signed up with.");
    setBusy(true);
    const r = await onForgotPassword(email.trim());
    setBusy(false);
    if (!r?.ok) return fail("email", r?.error || "Couldn't send the link. Try again.");
    setLeft(RESEND_SECONDS);
    if (mode !== "sent") go("sent");
  }

  const firstName = doneName.split(/\s+/)[0] || "";

  const emailField = (autoFocus) => (
    <Field id="si-email" label="Email" error={errFor("email")}>
      <input id="si-email" key={shakeK("email")}
        className={"si-input" + (error.field === "email" ? " si-shake" : "")}
        type="email" autoComplete="email" autoFocus={autoFocus} placeholder="you@example.com"
        value={email} onChange={(e) => { setEmail(e.target.value); clear(); }} />
    </Field>
  );

  return (
    <section className="si-card" aria-labelledby="si-title">
      <Stage stepKey={mode} dir={dir}>
        {mode === "signin" && (
          <>
            <header className="si-head">
              <h1 id="si-title">Sign in</h1>
              <p>Welcome back. Your cart and saved addresses are waiting.</p>
            </header>
            <form onSubmit={submitSignIn} noValidate className="si-form">
              {emailField(true)}
              <Field id="si-pw" label="Password" error={errFor("password")} hint={caps ? "Caps Lock is on." : ""}
                trailing={<button type="button" className="si-link si-right" onClick={() => go("forgot")}>Forgot password?</button>}>
                <PasswordInput id="si-pw" key={shakeK("password")} value={password}
                  shake={error.field === "password"} invalid={!!errFor("password")} autoComplete="current-password"
                  onCaps={setCaps} onChange={(v) => { setPassword(v); clear(); }} />
              </Field>
              <label className="si-check">
                <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} />
                <Check />
                Keep me signed in on this device
              </label>
              <button className="si-btn" type="submit" disabled={busy}>
                {busy ? <><Spinner />Signing in…</> : "Sign in"}
              </button>
            </form>
            <div className="si-or"><span>New to 369 Mart?</span></div>
            <button type="button" className="si-ghost" onClick={() => go("create")}>Create an account</button>
            {onGuest && (
              <button type="button" className="si-guest" onClick={onGuest}>
                Continue as guest <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 6l6 6-6 6" /></svg>
              </button>
            )}
          </>
        )}

        {mode === "create" && (
          <>
            <button type="button" className="si-back-btn" onClick={() => go("signin", -1)}><BackIcon />Sign in instead</button>
            <header className="si-head">
              <h1 id="si-title">Create your account</h1>
              <p>Takes under a minute. Checkout is faster from your next order.</p>
            </header>
            <form onSubmit={submitCreate} noValidate className="si-form">
              <Field id="si-name" label="Full name" error={errFor("name")}>
                <input id="si-name" key={shakeK("name")}
                  className={"si-input" + (error.field === "name" ? " si-shake" : "")}
                  autoComplete="name" autoFocus placeholder="As on your delivery label"
                  value={name} onChange={(e) => { setName(e.target.value); clear(); }} />
              </Field>
              {emailField(false)}
              <Field id="si-npw" label="Password" error={errFor("password")}
                hint={caps ? "Caps Lock is on." : "At least 8 characters. Mix letters, numbers and a symbol."}>
                <PasswordInput id="si-npw" key={shakeK("password")} value={password}
                  shake={error.field === "password"} invalid={!!errFor("password")} autoComplete="new-password"
                  onCaps={setCaps} onChange={(v) => { setPassword(v); clear(); }} />
                <div className="si-meter" data-score={pwScore} aria-live="polite">
                  <span /><span /><span /><span />
                  <em>{STRENGTH[pwScore]}</em>
                </div>
              </Field>
              <label className={"si-check" + (error.field === "agree" ? " si-check-err" : "")}>
                <input type="checkbox" checked={agree} onChange={(e) => { setAgree(e.target.checked); clear(); }} />
                <Check />
                <span>I agree to the <a href="/terms">Terms of Use</a> and <a href="/privacy">Privacy Policy</a></span>
              </label>
              {errFor("agree") && <p className="si-err" role="alert">{errFor("agree")}</p>}
              <button className="si-btn" type="submit" disabled={busy}>
                {busy ? <><Spinner />Creating account…</> : "Create account"}
              </button>
            </form>
          </>
        )}

        {mode === "forgot" && (
          <>
            <button type="button" className="si-back-btn" onClick={() => go("signin", -1)}><BackIcon />Back to sign in</button>
            <header className="si-head">
              <span className="si-badge" aria-hidden="true">
                <svg viewBox="0 0 24 24"><rect x="4" y="10" width="16" height="11" rx="2.5" /><path d="M8 10V7a4 4 0 0 1 8 0v3" /></svg>
              </span>
              <h1 id="si-title">Reset your password</h1>
              <p>Enter your account email and we'll send you a link to set a new password.</p>
            </header>
            <form onSubmit={submitForgot} noValidate className="si-form">
              {emailField(true)}
              <button className="si-btn" type="submit" disabled={busy}>
                {busy ? <><Spinner />Sending link…</> : "Send reset link"}
              </button>
            </form>
          </>
        )}

        {mode === "sent" && (
          <div className="si-done">
            <span className="si-badge si-mail" aria-hidden="true">
              <svg viewBox="0 0 24 24"><rect x="3" y="5" width="18" height="14" rx="2.5" /><path d="M3.5 6.5l8.5 6.5 8.5-6.5" /></svg>
            </span>
            <h1 id="si-title">Check your inbox</h1>
            <p>We sent a reset link to <b>{email.trim()}</b>.</p>
            <button className="si-btn" type="button" onClick={() => go("signin", -1)}>Back to sign in</button>
            <p className="si-resend" aria-live="polite">
              {left > 0 ? <>Resend link in <b>0:{String(left).padStart(2, "0")}</b></> :
                <>Didn't get it? Check spam, or <button type="button" className="si-link" onClick={() => submitForgot()}>resend link</button></>}
            </p>
          </div>
        )}

        {mode === "done" && (
          <div className="si-done">
            <svg className="si-done-mark" viewBox="0 0 64 64" aria-hidden="true">
              <circle cx="32" cy="32" r="28" /><path d="M20 33l8 8 16-17" />
            </svg>
            <h1 id="si-title">{firstName ? `You're in, ${firstName}` : "You're signed in"}</h1>
            <p>Your cart and saved addresses now follow you on every device.</p>
            <button className="si-btn" type="button" onClick={onDone}>Continue shopping</button>
          </div>
        )}
      </Stage>

      {mode === "signin" && (
        <p className="si-legal">
          By continuing you agree to 369 Mart's <a href="/terms">Terms of Use</a> and <a href="/privacy">Privacy Policy</a>.
        </p>
      )}
    </section>
  );
}

const TILES = [
  { i: "AC", name: "Arabica Coffee Beans", price: "₹649", col: "#1f7a4c" },
  { i: "BS", name: "Bluetooth Speaker 20W", price: "₹1,899", col: "#1b6ea3" },
  { i: "OW", name: "Organic Whole Wheat Atta", price: "₹359", col: "#b85a1c" },
];

export function SignInAside() {
  return (
    <aside className="si-aside" aria-label="Why sign in">
      <div className="si-aside-copy">
        <p className="si-eyebrow">369 Mart account</p>
        <h2>Your cart, addresses and offers — on every device.</h2>
        <ul className="si-perks">
          <li><span><svg viewBox="0 0 24 24"><path d="M3 7h11v9H3zM14 10h4l3 3v3h-7" /><circle cx="7" cy="17.5" r="1.8" /><circle cx="17" cy="17.5" r="1.8" /></svg></span>Track every order live, from packing to your door</li>
          <li><span><svg viewBox="0 0 24 24"><path d="M12 21s-7-6.2-7-11.5A7 7 0 0 1 19 9.5C19 14.8 12 21 12 21z" /><circle cx="12" cy="9.5" r="2.5" /></svg></span>Saved addresses for one-tap checkout</li>
          <li><span><svg viewBox="0 0 24 24"><path d="M3 12V4h8l10 10-8 8z" /><circle cx="7.5" cy="8.5" r="1.4" /></svg></span>Member prices on daily essentials</li>
          <li><span><svg viewBox="0 0 24 24"><path d="M4 12a8 8 0 1 0 2.4-5.7" /><path d="M4 4v4.5h4.5" /></svg></span>Reorder your usual basket in one tap</li>
        </ul>
      </div>
      <div className="si-tiles" aria-hidden="true">
        {TILES.map((t, n) => (
          <div className="si-tile" key={t.i} style={{ "--n": n, "--c": t.col }}>
            <div className="si-tile-img"><b>{t.i}</b></div>
            <div className="si-tile-txt"><span>{t.name}</span><strong>{t.price}</strong></div>
          </div>
        ))}
      </div>
      <p className="si-trust">
        <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="5" y="10" width="14" height="10" rx="2" /><path d="M8 10V7a4 4 0 0 1 8 0v3" /></svg>
        Encrypted sign-in. We never share or sell your email.
      </p>
    </aside>
  );
}

export default function SignInPage(props) {
  return (
    <main className="si-page">
      <a className="si-crumb" href="/">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M15 6l-6 6 6 6" /></svg>Back to shopping
      </a>
      <div className="si-grid">
        <SignInAside />
        <SignInCard {...props} />
      </div>
    </main>
  );
}
