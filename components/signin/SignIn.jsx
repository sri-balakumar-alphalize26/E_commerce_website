"use client";
/* ==========================================================================
   369 Mart — Sign in with your mobile number
   Number -> WhatsApp code -> in.  Create account = name + number -> code.
   "Sign in with email instead" for accounts made with an email; those are
   then asked once to add (and prove) a number.

   The mobile number is the customer's identity: it is the only thing a
   WhatsApp order and a website account share, so signing in by number is
   what brings the WhatsApp orders, addresses and wallet into the account.
   The code proves the phone is theirs - nobody can type someone else's
   number and open their account.

   Wire the backend through the props (all return Promises). Every prop has a
   demo default so the page works before the server is connected (demo code:
   123456).
   ========================================================================== */
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { clearReferral, takeReferral } from "@/lib/referral";
import CountryPicker from "./CountryPicker";

const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const demo = {
  phoneForm: async () => ({
    ok: true, country: { code: "IN", name: "India", dial: "+91" },
    countries: [{ code: "IN", name: "India", dial: "+91" }, { code: "OM", name: "Oman", dial: "+968" }],
    phone: { length: 10, example: "9876543210" },
  }),
  phoneStart: async () => { await wait(700); return { ok: true, message: "We sent a 6-digit code to your WhatsApp.", resendIn: 60 }; },
  phoneVerify: async ({ code }) => {
    await wait(700);
    return code === "123456" ? { ok: true, name: "", joined: { orders: 0, addresses: 0 } }
      : { ok: false, field: "code", error: "That code is not right." };
  },
  emailSignIn: async (_email, password) => {
    await wait(900);
    if (password.length < 6) return { ok: false, error: "Email or password is incorrect." };
    return { ok: true, name: "" };
  },
  forgotPassword: async () => { await wait(900); return { ok: true }; },
};
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;
const RESEND_SECONDS = 30;
const CODE_RESEND_SECONDS = 60;

const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;

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

/* Country chip + number. The chip opens a searchable list in the shop's own
   look (CountryPicker): type "india" or "91", Enter picks it. */
export function PhoneInput({ id, countries, country, onCountry, home, value, onChange, shake, invalid, placeholder, autoFocus }) {
  const input = useRef(null);
  return (
    <div className={"si-phone si-input" + (shake ? " si-shake" : "")}>
      <CountryPicker countries={countries} value={country} onChange={onCountry} home={home}
        onPicked={() => input.current?.focus()} />
      <input ref={input} id={id} type="tel" inputMode="tel" autoComplete="tel-national" autoFocus={autoFocus}
        aria-invalid={invalid || undefined} placeholder={placeholder}
        value={value} onChange={(e) => onChange(e.target.value.replace(/[^\d\s+()-]/g, ""))} />
    </div>
  );
}

/* Six boxes; typing moves on, Backspace moves back, a pasted or autofilled
   code fills them all. */
function CodeInput({ value, onChange, shake, onComplete }) {
  const refs = useRef([]);
  const digits = (value + "      ").slice(0, 6).split("");
  const set = (next) => {
    const clean = next.replace(/\D/g, "").slice(0, 6);
    onChange(clean);
    if (clean.length === 6) onComplete?.(clean);
  };
  return (
    <div className={"si-otp" + (shake ? " si-shake" : "")} role="group" aria-label="6-digit code">
      {digits.map((d, i) => (
        <input key={i} ref={(el) => (refs.current[i] = el)} style={{ "--i": i }}
          className={d.trim() ? "si-filled" : ""} inputMode="numeric" maxLength={i === 0 ? 6 : 1}
          autoComplete={i === 0 ? "one-time-code" : "off"} autoFocus={i === 0} aria-label={`Digit ${i + 1}`}
          value={d.trim()}
          onChange={(e) => {
            const typed = e.target.value.replace(/\D/g, "");
            if (typed.length > 1) { set(typed); refs.current[Math.min(typed.length, 5)]?.focus(); return; }
            const arr = value.split("");
            arr[i] = typed;
            set(arr.join("").slice(0, 6));
            if (typed && i < 5) refs.current[i + 1]?.focus();
          }}
          onKeyDown={(e) => {
            if (e.key === "Backspace" && !digits[i].trim() && i > 0) refs.current[i - 1]?.focus();
          }}
          onPaste={(e) => {
            const text = (e.clipboardData?.getData("text") || "").replace(/\D/g, "");
            if (text) { e.preventDefault(); set(text); refs.current[Math.min(text.length, 5)]?.focus(); }
          }} />
      ))}
    </div>
  );
}

const Check = () => (
  <span className="si-box" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M5 12.5l4.5 4.5L19 7.5" /></svg></span>
);
const BackIcon = () => <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M15 6l-6 6 6 6" /></svg>;

export function SignInCard({
  onPhoneForm = demo.phoneForm,
  onPhoneStart = demo.phoneStart,
  onPhoneVerify = demo.phoneVerify,
  onAddPhoneStart = demo.phoneStart,
  onAddPhoneVerify = demo.phoneVerify,
  onEmailSignIn = demo.emailSignIn,
  onForgotPassword = demo.forgotPassword,
  onDone = () => {},
  onGuest,
  initialMode = "signin",
}) {
  /* phone | code | password | email | create | addphone | forgot | sent | done */
  const [mode, setMode] = useState(initialMode === "signin" ? "phone" : initialMode);
  const [dir, setDir] = useState(1);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState({ field: "", msg: "" });
  const [shakeKey, setShakeKey] = useState(0);
  const [notice, setNotice] = useState("");

  const [countries, setCountries] = useState([]);
  const [country, setCountry] = useState("");
  const [home, setHome] = useState(""); /* the shop's own country, pinned atop the list */
  const [hint, setHint] = useState(null);
  const [phone, setPhone] = useState("");
  const [purpose, setPurpose] = useState("signin"); /* signin | signup | add */
  const [otp, setOtp] = useState("");
  const [codeLeft, setCodeLeft] = useState(0);
  const [sentMsg, setSentMsg] = useState("");
  const [joined, setJoined] = useState(null);

  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [caps, setCaps] = useState(false);
  const [agree, setAgree] = useState(true);
  const [left, setLeft] = useState(0);
  const [doneName, setDoneName] = useState("");
  const [code, setCode] = useState("");

  /* An invite link dropped the code here on its way past. Read it once the
     page is up rather than during render - localStorage does not exist on the
     server, and this component renders there first. */
  useEffect(() => {
    const saved = takeReferral();
    if (saved) setCode(saved);
  }, []);

  /* The default country comes from the shop's database (the company's
     country), never a hard-coded +91. */
  useEffect(() => {
    let live = true;
    Promise.resolve(onPhoneForm()).then((r) => {
      if (!live || !r?.ok) return;
      setCountries(r.countries || []);
      setCountry((c) => c || r.country?.code || "");
      setHome(r.country?.code || "");
      setHint(r.phone || null);
    }).catch(() => {});
    return () => { live = false; };
  }, [onPhoneForm]);

  const emailOk = EMAIL_RE.test(email.trim());

  useEffect(() => {
    if (mode !== "sent" || left <= 0) return;
    const t = setTimeout(() => setLeft((s) => s - 1), 1000);
    return () => clearTimeout(t);
  }, [mode, left]);
  useEffect(() => {
    if (codeLeft <= 0) return;
    const t = setTimeout(() => setCodeLeft((s) => s - 1), 1000);
    return () => clearTimeout(t);
  }, [codeLeft]);

  const go = (next, d = 1) => { setDir(d); setError({ field: "", msg: "" }); setNotice(""); setPassword(""); setMode(next); };
  const fail = (field, msg) => { setError({ field, msg }); setShakeKey((k) => k + 1); };
  const clear = () => { if (error.msg) setError({ field: "", msg: "" }); };
  const errFor = (f) => (error.field === f ? error.msg : "");
  const shakeK = (f) => f + (error.field === f ? shakeKey : 0);
  const dial = (countries.find((c) => c.code === country) || {}).dial || "";
  const shownNumber = `${dial} ${phone.trim()}`.trim();

  /* ---------------------------------------------------------- the code */

  async function sendCode(forPurpose) {
    const body = { phone: phone.trim(), country, purpose: forPurpose };
    if (forPurpose === "signup") body.name = name.trim();
    setBusy(true);
    const r = forPurpose === "add" ? await onAddPhoneStart(body) : await onPhoneStart(body);
    setBusy(false);
    return r;
  }

  async function submitPhone(e) {
    e.preventDefault();
    if (!phone.trim()) return fail("phone", "Enter your mobile number.");
    const r = await sendCode("signin");
    if (!r?.ok) {
      if (r?.signup) setNotice("signup");
      return fail("phone", r?.error || "Couldn't send the code. Try again.");
    }
    setPurpose("signin"); setOtp(""); setSentMsg(r.message || ""); setCodeLeft(r.resendIn || CODE_RESEND_SECONDS);
    go("code");
  }

  async function submitCreate(e) {
    e.preventDefault();
    if (name.trim().length < 2) return fail("name", "Enter your name as it should appear on deliveries.");
    if (!phone.trim()) return fail("phone", "Enter your mobile number.");
    if (!agree) return fail("agree", "Accept the Terms to create an account.");
    const r = await sendCode("signup");
    if (!r?.ok) {
      if (r?.signin) {
        /* Already a customer: straight to signing in, number filled in. */
        go("phone", -1);
        setNotice("signin");
        return;
      }
      return fail(r?.field || "phone", r?.error || "Couldn't send the code. Try again.");
    }
    setPurpose("signup"); setOtp(""); setSentMsg(r.message || ""); setCodeLeft(r.resendIn || CODE_RESEND_SECONDS);
    go("code");
  }

  async function submitAddPhone(e) {
    e.preventDefault();
    if (!phone.trim()) return fail("phone", "Enter your mobile number.");
    const r = await sendCode("add");
    if (!r?.ok) return fail("phone", r?.error || "Couldn't send the code. Try again.");
    setPurpose("add"); setOtp(""); setSentMsg(r.message || ""); setCodeLeft(r.resendIn || CODE_RESEND_SECONDS);
    go("code");
  }

  async function resend() {
    setError({ field: "", msg: "" });
    const r = await sendCode(purpose);
    if (!r?.ok) return fail("code", r?.error || "Couldn't send the code. Try again.");
    setOtp(""); setSentMsg(r.message || ""); setCodeLeft(r.resendIn || CODE_RESEND_SECONDS);
  }

  async function verify(value = otp, withPassword) {
    if (value.length !== 6) return fail("code", "Enter the 6-digit code.");
    const body = { phone: phone.trim(), country, purpose: purpose === "add" ? undefined : purpose, code: value };
    if (purpose === "signup") { body.name = name.trim(); body.referral = code.trim().toUpperCase() || undefined; }
    if (withPassword) body.password = withPassword;
    setBusy(true);
    const r = purpose === "add" ? await onAddPhoneVerify(body) : await onPhoneVerify(body);
    setBusy(false);
    if (!r?.ok) {
      if (r?.needPassword) {
        if (mode !== "password") { go("password"); return; }
        return fail("password", r.error);
      }
      if (r?.field === "password") return fail("password", r.error);
      return fail("code", r?.error || "That code is not right.");
    }
    if (purpose === "signup") clearReferral();
    setJoined(r.joined || null);
    setDoneName(r.name || name.trim());
    go("done");
  }

  /* ---------------------------------------------------------- email */

  async function submitEmail(e) {
    e.preventDefault();
    if (!email.trim()) return fail("email", "Enter your email or name.");
    if (!password) return fail("password", "Enter your password.");
    setBusy(true);
    const r = await onEmailSignIn(email.trim(), password, true);
    setBusy(false);
    if (!r?.ok) return fail("password", r?.error || "Email or password is incorrect.");
    setDoneName(r.name || "");
    /* An account with no proven number adds one before anything else. */
    if (r.needPhone) { setPhone(""); go("addphone"); return; }
    go("done");
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
  const phonePlaceholder = hint?.example || "Mobile number";

  const phoneField = (autoFocus, label = "Mobile number") => (
    <Field id="si-phone" label={label} error={errFor("phone")}
      hint={countries.length ? "We'll send a 6-digit code to this number on WhatsApp." : ""}>
      <PhoneInput id="si-phone" key={shakeK("phone")} countries={countries.length ? countries : [{ code: country, dial: "" }]}
        country={country} home={home} onCountry={(c) => { setCountry(c); clear(); }}
        value={phone} onChange={(v) => { setPhone(v); clear(); setNotice(""); }}
        shake={error.field === "phone"} invalid={!!errFor("phone")} placeholder={phonePlaceholder} autoFocus={autoFocus} />
    </Field>
  );

  const emailField = (autoFocus, { label = "Email", loose = false } = {}) => (
    <Field id="si-email" label={label} error={errFor("email")}>
      <input id="si-email" key={shakeK("email")}
        className={"si-input" + (error.field === "email" ? " si-shake" : "")}
        type={loose ? "text" : "email"} autoComplete={loose ? "username" : "email"} autoFocus={autoFocus} placeholder={loose ? "you@example.com or your name" : "you@example.com"}
        value={email} onChange={(e) => { setEmail(e.target.value); clear(); }} />
    </Field>
  );

  return (
    <section className="si-card" aria-labelledby="si-title">
      <Stage stepKey={mode} dir={dir}>
        {mode === "phone" && (
          <>
            <header className="si-head">
              <h1 id="si-title">Sign in</h1>
              <p>Use the mobile number you shop with - on the website, the app or WhatsApp.</p>
            </header>
            {notice === "signin" && (
              <p className="si-note" role="status">You already have an account with this number. Sign in below.</p>
            )}
            <form onSubmit={submitPhone} noValidate className="si-form">
              {phoneField(true)}
              {notice === "signup" && (
                <button type="button" className="si-ghost" onClick={() => go("create")}>Create an account with this number</button>
              )}
              <button className="si-btn" type="submit" disabled={busy}>
                {busy ? <><Spinner />Sending code…</> : "Continue"}
              </button>
            </form>
            <p className="si-alt">
              <button type="button" className="si-link" onClick={() => go("email")}>Sign in with email instead</button>
            </p>
            <div className="si-or"><span>New to 369 Mart?</span></div>
            <button type="button" className="si-ghost" onClick={() => go("create")}>Create an account</button>
            {onGuest && (
              <button type="button" className="si-guest" onClick={onGuest}>
                Continue as guest <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 6l6 6-6 6" /></svg>
              </button>
            )}
          </>
        )}

        {mode === "code" && (
          <>
            <button type="button" className="si-back-btn"
              onClick={() => go(purpose === "signup" ? "create" : purpose === "add" ? "addphone" : "phone", -1)}>
              <BackIcon />Change number
            </button>
            <header className="si-head">
              <span className="si-badge si-wa" aria-hidden="true">
                <svg viewBox="0 0 24 24"><path d="M4 20l1.3-3.9A8 8 0 1 1 8 19z" /><path d="M9 9.5c0 3 2.5 5.5 5.5 5.5l1.2-1.4-2-1-1 1a4 4 0 0 1-2.3-2.3l1-1-1-2z" /></svg>
              </span>
              <h1 id="si-title">Enter the code</h1>
              <p>{sentMsg || "We sent a 6-digit code to your WhatsApp."} <b>{shownNumber}</b></p>
            </header>
            <form onSubmit={(e) => { e.preventDefault(); verify(); }} noValidate className="si-form">
              <CodeInput key={shakeK("code")} value={otp} shake={error.field === "code"}
                onChange={(v) => { setOtp(v); clear(); }} onComplete={(v) => { if (!busy) verify(v); }} />
              {errFor("code") && <p className="si-err" role="alert">{errFor("code")}</p>}
              <button className="si-btn" type="submit" disabled={busy}>
                {busy ? <><Spinner />Checking…</> : purpose === "add" ? "Confirm number" : "Sign in"}
              </button>
            </form>
            <p className="si-resend" aria-live="polite">
              {codeLeft > 0 ? <>Resend code in <b>0:{String(codeLeft).padStart(2, "0")}</b></> :
                <>Didn't get it? <button type="button" className="si-link" disabled={busy} onClick={resend}>Send a new code</button></>}
            </p>
          </>
        )}

        {mode === "password" && (
          <>
            <button type="button" className="si-back-btn" onClick={() => go("code", -1)}><BackIcon />Back</button>
            <header className="si-head">
              <h1 id="si-title">Confirm it's your account</h1>
              <p>This number was saved on an account but never confirmed. Enter that account's password once - after this, your number is enough.</p>
            </header>
            <form onSubmit={(e) => { e.preventDefault(); if (!password) return fail("password", "Enter your password."); verify(otp, password); }}
              noValidate className="si-form">
              <Field id="si-cpw" label="Password" error={errFor("password")} hint={caps ? "Caps Lock is on." : ""}>
                <PasswordInput id="si-cpw" key={shakeK("password")} value={password}
                  shake={error.field === "password"} invalid={!!errFor("password")} autoComplete="current-password"
                  onCaps={setCaps} onChange={(v) => { setPassword(v); clear(); }} />
              </Field>
              <button className="si-btn" type="submit" disabled={busy}>
                {busy ? <><Spinner />Signing in…</> : "Sign in"}
              </button>
            </form>
          </>
        )}

        {mode === "email" && (
          <>
            <button type="button" className="si-back-btn" onClick={() => go("phone", -1)}><BackIcon />Sign in with mobile number</button>
            <header className="si-head">
              <h1 id="si-title">Sign in with email</h1>
              <p>For accounts made with an email. You'll add your mobile number next, once.</p>
            </header>
            <form onSubmit={submitEmail} noValidate className="si-form">
              {emailField(true, { label: "Email or name", loose: true })}
              <Field id="si-pw" label="Password" error={errFor("password")} hint={caps ? "Caps Lock is on." : ""}
                trailing={<button type="button" className="si-link si-right" onClick={() => go("forgot")}>Forgot password?</button>}>
                <PasswordInput id="si-pw" key={shakeK("password")} value={password}
                  shake={error.field === "password"} invalid={!!errFor("password")} autoComplete="current-password"
                  onCaps={setCaps} onChange={(v) => { setPassword(v); clear(); }} />
              </Field>
              <button className="si-btn" type="submit" disabled={busy}>
                {busy ? <><Spinner />Signing in…</> : "Sign in"}
              </button>
            </form>
          </>
        )}

        {mode === "addphone" && (
          <>
            <header className="si-head">
              <h1 id="si-title">Add your mobile number</h1>
              <p>Your number is how 369 Mart knows you - on the website, the app and WhatsApp. Any orders you placed on WhatsApp join your account.</p>
            </header>
            <form onSubmit={submitAddPhone} noValidate className="si-form">
              {phoneField(true)}
              <button className="si-btn" type="submit" disabled={busy}>
                {busy ? <><Spinner />Sending code…</> : "Send code on WhatsApp"}
              </button>
            </form>
          </>
        )}

        {mode === "create" && (
          <>
            <button type="button" className="si-back-btn" onClick={() => go("phone", -1)}><BackIcon />Sign in instead</button>
            <header className="si-head">
              <h1 id="si-title">Create your account</h1>
              <p>Your name and mobile number. Already ordered on WhatsApp? Those orders come with you.</p>
            </header>
            <form onSubmit={submitCreate} noValidate className="si-form">
              <Field id="si-name" label="Full name" error={errFor("name")}>
                <input id="si-name" key={shakeK("name")}
                  className={"si-input" + (error.field === "name" ? " si-shake" : "")}
                  autoComplete="name" autoFocus placeholder="As on your delivery label"
                  value={name} onChange={(e) => { setName(e.target.value); clear(); }} />
              </Field>
              {phoneField(false)}
              <Field id="si-code" label="Referral code" error={errFor("code")}
                hint="Optional. If a friend invited you, their reward lands when you order.">
                <input id="si-code" className="si-input si-code"
                  autoComplete="off" placeholder="369ABCD"
                  value={code}
                  onChange={(e) => { setCode(e.target.value.toUpperCase()); clear(); }} />
              </Field>
              <label className={"si-check" + (error.field === "agree" ? " si-check-err" : "")}>
                <input type="checkbox" checked={agree} onChange={(e) => { setAgree(e.target.checked); clear(); }} />
                <Check />
                <span>I agree to the <a href="/terms">Terms of Use</a> and <a href="/privacy">Privacy Policy</a></span>
              </label>
              {errFor("agree") && <p className="si-err" role="alert">{errFor("agree")}</p>}
              <button className="si-btn" type="submit" disabled={busy}>
                {busy ? <><Spinner />Sending code…</> : "Continue"}
              </button>
            </form>
          </>
        )}

        {mode === "forgot" && (
          <>
            <button type="button" className="si-back-btn" onClick={() => go("email", -1)}><BackIcon />Back to sign in</button>
            <header className="si-head">
              <span className="si-badge" aria-hidden="true">
                <svg viewBox="0 0 24 24"><rect x="4" y="10" width="16" height="11" rx="2.5" /><path d="M8 10V7a4 4 0 0 1 8 0v3" /></svg>
              </span>
              <h1 id="si-title">Reset your password</h1>
              <p>Enter your account email and we'll send you a link to set a new password. Or <button type="button" className="si-link" onClick={() => go("phone", -1)}>sign in with your mobile number</button> - no password needed.</p>
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
            <button className="si-btn" type="button" onClick={() => go("email", -1)}>Back to sign in</button>
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
            {joined && (joined.orders > 0 || joined.addresses > 0) ? (
              <p>We found {plural(joined.orders, "WhatsApp order", "WhatsApp orders")} and {plural(joined.addresses, "address", "addresses")} - they're in your account now.</p>
            ) : (
              <p>Your cart, orders and saved addresses now follow you on every device.</p>
            )}
            <button className="si-btn" type="button" onClick={onDone}>Continue shopping</button>
          </div>
        )}
      </Stage>

      {(mode === "phone" || mode === "create") && (
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
  { i: "SSD", name: "Samsung 990 PRO 1TB NVMe", price: "₹9,800", col: "#155c86" },
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
          <li><span><svg viewBox="0 0 24 24"><path d="M3 12V4h8l10 10-8 8z" /><circle cx="7.5" cy="8.5" r="1.4" /></svg></span>Member prices on everyday electricals</li>
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
