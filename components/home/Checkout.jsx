"use client";
/* ==========================================================================
   369 Mart — Checkout & payment   (/checkout)
   Progress: Cart ✓ — Address — Slot — Payment — Done (line fills as you go)
   1 Delivery address  saved addresses (animated radio), add a new one inline
   2 Delivery slot     Quick: now or a scheduled slot · Express: standard / priority
   3 Payment           369 Wallet toggle · UPI apps or UPI ID (verify) · cards
                       (saved card + new card with a live card that flips for CVV)
                       · net banking · cash on delivery
   Right: order summary (items, bill, savings) with the Pay button.
   Pay → sheet: approve in UPI app (countdown ring) · bank OTP (6 boxes) ·
   bank redirect · placing order → success burst → receipt printer.
   Failure: red cross draws, card shakes, retry or change method.
   ========================================================================== */
import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Icon, Thumb, inr } from "./shared";
import { Amount, CART_RULES, COUPONS, computeBill } from "./Cart";
import {
  BANKS, BRAND_LABEL, COD_LIMIT, SAVED_CARDS, UPI_APPS, cardBrand, demoGateway, expiryOk,
  formatCard, formatExpiry, luhn, newOrderId, upiOk,
} from "./payment";

const PRIORITY_FEE = 49;
const reduced = () => typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

/* ---------------- slots ---------------- */
function useSlots() {
  return useMemo(() => {
    const now = new Date();
    const day = (n) => { const d = new Date(now); d.setDate(d.getDate() + n); return d.toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short" }); };
    const quick = [{ key: "now", top: "Now", sub: "10–20 min", label: "Arriving in 10–20 mins" }];
    if (now.getHours() < 17) quick.push({ key: "eve", top: "Today", sub: "6 – 8 PM", label: "Today, 6 – 8 PM" });
    quick.push({ key: "tm", top: "Tomorrow", sub: "8 – 10 AM", label: `${day(1)}, 8 – 10 AM` });
    quick.push({ key: "te", top: "Tomorrow", sub: "6 – 8 PM", label: `${day(1)}, 6 – 8 PM` });
    const all = [
      { key: "std", top: "Standard", sub: `By ${day(3)}`, label: `Arrives by ${day(3)}`, fee: 0 },
      { key: "pri", top: "Priority", sub: `By ${day(1)}`, label: `Arrives by ${day(1)}`, fee: PRIORITY_FEE },
    ];
    return { quick, all };
  }, []);
}

/* ---------------- building blocks ---------------- */
function Progress({ step }) {
  const labels = ["Cart", "Address", "Slot", "Payment"];
  return (
    <ol className="co-progress" style={{ "--p": Math.min(step, 3) / 3 }} aria-label="Checkout progress">
      <i className="co-progress-line" aria-hidden="true"><b /></i>
      {labels.map((l, k) => (
        <li key={l} className={k < step ? "co-done" : k === step ? "co-now" : ""} aria-current={k === step ? "step" : undefined}>
          <span className="co-dot">{k < step ? <Icon n="check" size={12} /> : k + 1}</span>{l}
        </li>
      ))}
    </ol>
  );
}

function Step({ n, title, open, done, summary, onEdit, children, icon }) {
  return (
    <section className={"co-card co-step" + (open ? " co-open" : "") + (done ? " co-isdone" : "")} style={{ "--n": n }}>
      <header className="co-step-head">
        <span className="co-step-n">{done && !open ? <Icon n="check" size={14} /> : <Icon n={icon} size={16} />}</span>
        <div className="co-step-title">
          <h2>{title}</h2>
          {!open && summary && <p key={summary}>{summary}</p>}
        </div>
        {done && !open && <button className="co-link" onClick={onEdit}>Change</button>}
      </header>
      <div className="co-collapse"><div inert={!open}><div className="co-step-body">{children}</div></div></div>
    </section>
  );
}

function Radio({ on }) {
  return <span className={"co-radio" + (on ? " co-on" : "")} aria-hidden="true"><i /></span>;
}

/* ---------------- 1 address ---------------- */
function AddressStep({ addresses, setAddresses, selected, onSelect, onContinue }) {
  const [adding, setAdding] = useState(!addresses.length);
  const [d, setD] = useState({ label: "Home", name: "", phone: "", line: "", city: "", pin: "" });
  const [err, setErr] = useState({});
  const save = (e) => {
    e.preventDefault();
    const x = {};
    if (!d.name.trim()) x.name = "Enter the receiver's name";
    if (!/^[6-9]\d{9}$/.test(d.phone)) x.phone = "Enter a 10-digit mobile number";
    if (d.line.trim().length < 6) x.line = "Add house / flat and street";
    if (!d.city.trim()) x.city = "Enter city";
    if (!/^\d{6}$/.test(d.pin)) x.pin = "6-digit pincode";
    setErr(x);
    if (Object.keys(x).length) return;
    const a = { id: "a" + Date.now(), label: d.label, name: d.name.trim(), phone: d.phone, line: d.line.trim(), city: `${d.city.trim()} ${d.pin}`, icon: d.label === "Work" ? "brief" : d.label === "Home" ? "home" : "pin" };
    setAddresses([a, ...addresses]); onSelect(a); setAdding(false);
    setD({ label: "Home", name: "", phone: "", line: "", city: "", pin: "" });
  };
  const field = (k, label, props = {}) => (
    <label className={"co-field" + (err[k] ? " co-err" : "")}>
      <input value={d[k]} placeholder=" " onChange={(e) => { setD({ ...d, [k]: props.digits ? e.target.value.replace(/\D/g, "").slice(0, props.digits) : e.target.value }); setErr({ ...err, [k]: undefined }); }} inputMode={props.digits ? "numeric" : undefined} autoComplete={props.ac} />
      <span>{label}</span>
      {err[k] && <em key={err[k]}>{err[k]}</em>}
    </label>
  );
  return (
    <>
      <div className="co-addrs" role="radiogroup" aria-label="Delivery address">
        {addresses.map((a, i) => {
          const on = selected?.id === a.id;
          return (
            <button key={a.id} role="radio" aria-checked={on} className={"co-addr" + (on ? " co-on" : "")} style={{ "--i": i }} onClick={() => onSelect(a)}>
              <Radio on={on} />
              <span className="co-addr-ic"><Icon n={a.icon || "pin"} size={17} /></span>
              <span className="co-addr-txt">
                <b>{a.label}{a.name ? <small> · {a.name}</small> : null}</b>
                <span>{a.line}{a.city ? ", " + a.city : ""}</span>
                {a.phone && <span className="co-muted">+91 {a.phone}</span>}
              </span>
            </button>
          );
        })}
      </div>
      <div className={"co-grow" + (adding ? " co-show" : "")}>
        <div inert={!adding}>
          <form className="co-addr-form" onSubmit={save} noValidate>
            <div className="co-chips">
              {["Home", "Work", "Other"].map((l) => <button type="button" key={l} className={d.label === l ? "co-on" : ""} onClick={() => setD({ ...d, label: l })}>{l}</button>)}
            </div>
            <div className="co-form-grid">
              {field("name", "Receiver's name", { ac: "name" })}
              {field("phone", "Mobile number", { digits: 10, ac: "tel-national" })}
              <div className="co-span2">{field("line", "House / flat, street, area", { ac: "street-address" })}</div>
              {field("city", "City", { ac: "address-level2" })}
              {field("pin", "Pincode", { digits: 6, ac: "postal-code" })}
            </div>
            <div className="co-row-end">
              {addresses.length > 0 && <button type="button" className="co-ghost" onClick={() => setAdding(false)}>Cancel</button>}
              <button className="co-primary" type="submit">Save address</button>
            </div>
          </form>
        </div>
      </div>
      <div className="co-row-between">
        {!adding ? <button className="co-link co-add" onClick={() => setAdding(true)}><Icon n="plus" size={16} />Add a new address</button> : <span />}
        <button className="co-primary co-hide-m" disabled={!selected} onClick={onContinue}>Deliver here</button>
      </div>
    </>
  );
}

/* ---------------- 2 slot ---------------- */
function SlotStep({ bill, slots, slot, setSlot, onContinue }) {
  return (
    <>
      {["quick", "all"].map((g) => bill.groups[g].length > 0 && (
        <div key={g} className={"co-slotgroup co-slot-" + g}>
          <div className="co-slot-head">
            <b><Icon n={g === "quick" ? "bolt" : "truck"} size={15} className={g === "quick" ? "hm-fill" : ""} />{g === "quick" ? "Quick" : "Express"} · {bill.groups[g].reduce((s, l) => s + l.qty, 0)} items</b>
            <span className="co-thumbs">
              {bill.groups[g].slice(0, 5).map((l, k) => <span key={l.p.id} style={{ "--k": k }}><Thumb p={l.p} /></span>)}
              {bill.groups[g].length > 5 && <em>+{bill.groups[g].length - 5}</em>}
            </span>
          </div>
          <div className="co-slots" role="radiogroup" aria-label={`${g === "quick" ? "Quick" : "Express"} delivery slot`}>
            {slots[g].map((s, k) => {
              const on = slot[g] === s.key;
              return (
                <button key={s.key} role="radio" aria-checked={on} className={"co-slot" + (on ? " co-on" : "")} style={{ "--k": k }} onClick={() => setSlot({ ...slot, [g]: s.key })}>
                  <b>{s.top}</b><span>{s.sub}</span>
                  <small>{s.fee ? `+${inr(s.fee)}` : g === "quick" && s.key === "now" ? "Fastest" : "Free"}</small>
                </button>
              );
            })}
          </div>
        </div>
      ))}
      <div className="co-row-end"><button className="co-primary co-hide-m" onClick={onContinue}>Continue to payment</button></div>
    </>
  );
}

/* ---------------- 3 payment ---------------- */
function CardPreview({ num, name, exp, flipped, brand }) {
  const digits = num.replace(/\D/g, "");
  const shown = (formatCard(digits) || "").padEnd(19, "•").replace(/ /g, " ");
  return (
    <div className={"co-cc" + (flipped ? " co-flip" : "") + (brand ? " co-cc-" + brand : "")} aria-hidden="true">
      <div className="co-cc-in">
        <div className="co-cc-front">
          <span className="co-cc-chip" />
          <span className="co-cc-brand" key={brand || "none"}>{BRAND_LABEL[brand] || ""}</span>
          <span className="co-cc-num">{shown.split("").map((c, i) => <i key={i + c} className={c !== "•" && c !== " " ? "co-typed" : ""}>{c}</i>)}</span>
          <span className="co-cc-row"><span><small>Card holder</small>{name || "YOUR NAME"}</span><span><small>Expires</small>{exp || "MM/YY"}</span></span>
        </div>
        <div className="co-cc-back"><span className="co-cc-strip" /><span className="co-cc-cvv"><small>CVV</small>•••</span></div>
      </div>
    </div>
  );
}

function PaymentStep({ payable, pay, setPay, wallet, walletUse, setWalletUse, walletBal, codAllowed }) {
  const [verifying, setVerifying] = useState(false);
  const [cvvFocus, setCvvFocus] = useState(false);
  const set = (patch) => setPay((p) => ({ ...p, ...patch }));
  const verify = async () => {
    setVerifying(true);
    const r = await demoGateway.verifyUpi(pay.vpa);
    setVerifying(false);
    set({ vpaName: r.ok ? r.name : "", vpaError: r.ok ? "" : r.error });
  };
  const brand = cardBrand(pay.cardNum);

  const methods = [
    { key: "upi", icon: "upi", title: "UPI", sub: "Google Pay, PhonePe, Paytm or any UPI ID", badge: "Recommended" },
    { key: "card", icon: "card", title: "Credit / debit card", sub: "Visa, Mastercard, RuPay, Amex" },
    { key: "netbanking", icon: "bank", title: "Net banking", sub: "All major Indian banks" },
    { key: "cod", icon: "cash", title: "Cash on delivery", sub: codAllowed ? "Pay by cash or UPI at your door" : `Available on orders up to ${inr(COD_LIMIT)}`, disabled: !codAllowed },
  ];

  return (
    <>
      <label className={"co-wallet" + (walletUse ? " co-on" : "")}>
        <span className="co-wallet-ic"><Icon n="wallet" size={20} /></span>
        <span className="co-wallet-txt"><b>369 Wallet</b><small>Balance <Amount value={walletUse ? Math.max(0, walletBal - wallet.used) : walletBal} /></small></span>
        {walletUse && wallet.used > 0 && <em key={wallet.used} className="co-wallet-used">−{inr(wallet.used)}</em>}
        <input type="checkbox" checked={walletUse} disabled={walletBal <= 0} onChange={(e) => setWalletUse(e.target.checked)} />
        <i className="co-switch" aria-hidden="true" />
      </label>

      {wallet.covers ? (
        <div className="co-covered"><Icon n="check" size={16} />Your wallet covers this order. No other payment needed.</div>
      ) : (
        <div className="co-methods" role="radiogroup" aria-label="Payment method">
          {methods.map((m, i) => {
            const on = pay.method === m.key;
            return (
              <div key={m.key} className={"co-method" + (on ? " co-open" : "") + (m.disabled ? " co-disabled" : "")} style={{ "--i": i }}>
                <button className="co-method-head" role="radio" aria-checked={on} disabled={m.disabled} onClick={() => set({ method: m.key })}>
                  <Radio on={on} />
                  <span className="co-method-ic"><Icon n={m.icon} size={19} /></span>
                  <span className="co-method-txt"><b>{m.title}{m.badge && <em>{m.badge}</em>}</b><small>{m.sub}</small></span>
                </button>
                <div className="co-collapse"><div inert={!on}><div className="co-method-body">
                  {m.key === "upi" && (
                    <>
                      <div className="co-apps">
                        {UPI_APPS.map((a, k) => (
                          <button key={a.key} className={"co-app" + (pay.upiApp === a.key && !pay.useVpa ? " co-on" : "")} style={{ "--k": k, "--tone": a.tone }} onClick={() => set({ upiApp: a.key, useVpa: false })} tabIndex={on ? 0 : -1}>
                            <span className="co-app-logo">{a.short}</span><small>{a.name}</small>
                          </button>
                        ))}
                      </div>
                      <div className="co-or"><span>or pay with UPI ID</span></div>
                      <div className={"co-vpa" + (pay.vpaName ? " co-ok" : "") + (pay.vpaError ? " co-err" : "")}>
                        <label className="co-field">
                          <input value={pay.vpa} placeholder=" " autoComplete="off" autoCapitalize="none" tabIndex={on ? 0 : -1}
                            onFocus={() => set({ useVpa: true })}
                            onChange={(e) => set({ vpa: e.target.value.trim(), useVpa: true, vpaName: "", vpaError: "" })}
                            onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); if (upiOk(pay.vpa)) verify(); } }} />
                          <span>UPI ID (e.g. name@okaxis)</span>
                        </label>
                        <button className="co-verify" disabled={!upiOk(pay.vpa) || verifying || !!pay.vpaName} onClick={verify} tabIndex={on ? 0 : -1}>
                          {verifying ? <i className="co-spin" /> : pay.vpaName ? <><Icon n="check" size={14} />Verified</> : "Verify"}
                        </button>
                      </div>
                      {pay.vpaName && <p className="co-vpa-name" key={pay.vpaName}><Icon n="user" size={13} />{pay.vpaName}</p>}
                      {pay.vpaError && <p className="co-error" key={pay.vpaError}>{pay.vpaError}</p>}
                    </>
                  )}

                  {m.key === "card" && (
                    <>
                      <div className="co-saved">
                        {SAVED_CARDS.map((c) => (
                          <button key={c.id} className={"co-savedcard" + (pay.cardId === c.id ? " co-on" : "")} onClick={() => set({ cardId: c.id })} tabIndex={on ? 0 : -1}>
                            <Radio on={pay.cardId === c.id} />
                            <span className={"co-brandtag co-b-" + c.brand}>{BRAND_LABEL[c.brand]}</span>
                            <span><b>•••• {c.last4}</b><small>{c.bank} · expires {c.exp}</small></span>
                          </button>
                        ))}
                        <button className={"co-savedcard" + (pay.cardId === "new" ? " co-on" : "")} onClick={() => set({ cardId: "new" })} tabIndex={on ? 0 : -1}>
                          <Radio on={pay.cardId === "new"} /><span className="co-brandtag"><Icon n="plus" size={13} /></span><span><b>Add a new card</b><small>Saved securely for next time</small></span>
                        </button>
                      </div>
                      {pay.cardId !== "new" ? (
                        <label className="co-field co-cvv-only">
                          <input value={pay.savedCvv} placeholder=" " inputMode="numeric" type="password" autoComplete="cc-csc" tabIndex={on ? 0 : -1} onChange={(e) => set({ savedCvv: e.target.value.replace(/\D/g, "").slice(0, 4) })} />
                          <span>CVV</span>
                        </label>
                      ) : (
                        <div className="co-newcard">
                          <CardPreview num={pay.cardNum} name={pay.cardName} exp={pay.cardExp} flipped={cvvFocus} brand={brand} />
                          <div className="co-form-grid">
                            <label className={"co-field co-span2" + (pay.cardNum.replace(/\D/g, "").length >= 15 && !luhn(pay.cardNum) ? " co-err" : "")}>
                              <input value={pay.cardNum} placeholder=" " inputMode="numeric" autoComplete="cc-number" tabIndex={on ? 0 : -1} onChange={(e) => set({ cardNum: formatCard(e.target.value) })} />
                              <span>Card number</span>
                              {brand && <b className={"co-brandtag co-inline co-b-" + brand} key={brand}>{BRAND_LABEL[brand]}</b>}
                              {pay.cardNum.replace(/\D/g, "").length >= 15 && !luhn(pay.cardNum) && <em>Check the card number</em>}
                            </label>
                            <label className="co-field co-span2">
                              <input value={pay.cardName} placeholder=" " autoComplete="cc-name" tabIndex={on ? 0 : -1} onChange={(e) => set({ cardName: e.target.value.toUpperCase().slice(0, 26) })} />
                              <span>Name on card</span>
                            </label>
                            <label className={"co-field" + (pay.cardExp.length === 5 && !expiryOk(pay.cardExp) ? " co-err" : "")}>
                              <input value={pay.cardExp} placeholder=" " inputMode="numeric" autoComplete="cc-exp" tabIndex={on ? 0 : -1} onChange={(e) => set({ cardExp: formatExpiry(e.target.value) })} />
                              <span>Expiry (MM/YY)</span>
                              {pay.cardExp.length === 5 && !expiryOk(pay.cardExp) && <em>Invalid expiry</em>}
                            </label>
                            <label className="co-field">
                              <input value={pay.cardCvv} placeholder=" " inputMode="numeric" type="password" autoComplete="cc-csc" tabIndex={on ? 0 : -1}
                                onFocus={() => setCvvFocus(true)} onBlur={() => setCvvFocus(false)}
                                onChange={(e) => set({ cardCvv: e.target.value.replace(/\D/g, "").slice(0, brand === "amex" ? 4 : 3) })} />
                              <span>CVV</span>
                            </label>
                          </div>
                          <label className="co-check"><input type="checkbox" checked={pay.saveCard} onChange={(e) => set({ saveCard: e.target.checked })} tabIndex={on ? 0 : -1} /><span className="co-box"><Icon n="check" size={11} /></span>Save this card as per RBI guidelines</label>
                        </div>
                      )}
                    </>
                  )}

                  {m.key === "netbanking" && (
                    <>
                      <div className="co-banks">
                        {BANKS.slice(0, 6).map((b, k) => (
                          <button key={b.key} className={"co-bank" + (pay.bank === b.key ? " co-on" : "")} style={{ "--k": k, "--tone": b.tone }} onClick={() => set({ bank: b.key })} tabIndex={on ? 0 : -1}>
                            <span className="co-bank-logo">{b.short}</span><small>{b.name.replace(" Bank", "")}</small>
                          </button>
                        ))}
                      </div>
                      <label className="co-select">
                        <select value={pay.bank} onChange={(e) => set({ bank: e.target.value })} tabIndex={on ? 0 : -1}>
                          <option value="">Other banks</option>
                          {BANKS.map((b) => <option key={b.key} value={b.key}>{b.name}</option>)}
                        </select>
                        <Icon n="chev" size={16} />
                      </label>
                    </>
                  )}

                  {m.key === "cod" && (
                    <p className="co-codnote"><Icon n="info" size={16} />Keep exact change ready, or pay by scanning the rider's UPI QR at your door.</p>
                  )}
                </div></div></div>
              </div>
            );
          })}
        </div>
      )}
    </>
  );
}

/* ---------------- pay sheet: approve / OTP / redirect / result ---------------- */
function CountdownRing({ secs, total }) {
  const r = 34, c = 2 * Math.PI * r;
  const mm = String(Math.floor(secs / 60)).padStart(2, "0"), ss = String(secs % 60).padStart(2, "0");
  return (
    <span className="co-ring">
      <svg viewBox="0 0 80 80" aria-hidden="true"><circle cx="40" cy="40" r={r} className="co-ring-bg" /><circle cx="40" cy="40" r={r} className="co-ring-fg" style={{ strokeDasharray: c, strokeDashoffset: c * (1 - secs / total) }} /></svg>
      <b>{mm}:{ss}</b>
    </span>
  );
}

function OtpBoxes({ value, onChange, disabled, shake }) {
  const refs = useRef([]);
  /* focus the next empty box on open, after a wrong OTP and when verification ends */
  useEffect(() => { if (!disabled) refs.current[Math.min(value.length, 5)]?.focus(); }, [disabled]); // eslint-disable-line
  const put = (i, v) => {
    const digits = v.replace(/\D/g, "");
    if (!digits) return;
    const arr = value.padEnd(6, " ").split("");
    digits.split("").forEach((d, k) => { if (i + k < 6) arr[i + k] = d; });
    const next = arr.join("").replace(/\s+$/, "");
    onChange(next);
    refs.current[Math.min(i + digits.length, 5)]?.focus();
  };
  return (
    <div className={"co-otp" + (shake ? " co-shake" : "")} key={shake}>
      {Array.from({ length: 6 }, (_, i) => (
        <input key={i} ref={(el) => (refs.current[i] = el)} value={value[i] || ""} inputMode="numeric" autoComplete={i === 0 ? "one-time-code" : "off"} maxLength={6} disabled={disabled}
          className={value[i] ? "co-filled" : ""} aria-label={`OTP digit ${i + 1}`}
          onChange={(e) => put(i, e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Backspace") {
              e.preventDefault();
              const arr = value.split("");
              if (arr[i]) { arr[i] = ""; onChange(arr.join("").slice(0, i) + arr.slice(i + 1).join("")); }
              else if (i > 0) { onChange(value.slice(0, i - 1)); refs.current[i - 1]?.focus(); }
            }
          }} />
      ))}
    </div>
  );
}

function PaySheet({ job, amount, onDone, onFail, onCancel, onRetry, onChangeMethod }) {
  const [state, setState] = useState("working"); // working | otp | success | failed
  const [secs, setSecs] = useState(300);
  const [otp, setOtp] = useState("");
  const [otpBusy, setOtpBusy] = useState(false);
  const [otpErr, setOtpErr] = useState("");
  const [shake, setShake] = useState(0);
  const [resend, setResend] = useState(30);
  const [error, setError] = useState("");
  const [redirect, setRedirect] = useState(0);
  const alive = useRef(true);
  useEffect(() => {
    alive.current = true; /* StrictMode re-runs effects: restore the flag the cleanup cleared */
    document.documentElement.classList.add("ls-lock");
    return () => { alive.current = false; document.documentElement.classList.remove("ls-lock"); };
  }, []);

  const finish = (r) => {
    if (!alive.current) return;
    if (r.ok) { setState("success"); setTimeout(() => alive.current && onDone(r), reduced() ? 200 : 1300); }
    else { setError(r.error || "Payment could not be completed."); setState("failed"); onFail?.(); }
  };

  useEffect(() => {
    let t;
    (async () => {
      if (job.method === "upi") {
        t = setInterval(() => setSecs((s) => Math.max(0, s - 1)), 1000);
        finish(await demoGateway.collectUpi({ vpa: job.vpa }));
      } else if (job.method === "card") {
        await new Promise((r) => setTimeout(r, 1200));
        if (alive.current) setState("otp");
      } else if (job.method === "netbanking") {
        t = setInterval(() => setRedirect((n) => Math.min(3, n + 1)), 800);
        finish(await demoGateway.netbanking());
      } else if (job.method === "wallet") finish(await demoGateway.wallet());
      else finish(await demoGateway.cod());
    })();
    return () => clearInterval(t);
  }, []); // eslint-disable-line

  useEffect(() => {
    if (state !== "otp") return;
    const t = setInterval(() => setResend((s) => Math.max(0, s - 1)), 1000);
    return () => clearInterval(t);
  }, [state]);

  const submitOtp = async (code) => {
    setOtpBusy(true); setOtpErr("");
    const r = await demoGateway.verifyOtp({ otp: code, card: job.card });
    if (!alive.current) return;
    setOtpBusy(false);
    if (!r.ok && r.retry) { setOtpErr(r.error); setOtp(""); setShake((n) => n + 1); return; }
    finish(r);
  };
  useEffect(() => { if (state === "otp" && otp.length === 6 && !otpBusy) submitOtp(otp); }, [otp]); // eslint-disable-line

  const app = UPI_APPS.find((a) => a.key === job.upiApp);
  const bank = BANKS.find((b) => b.key === job.bank);

  /* portalled to .hm-page: the animated page wrapper would otherwise trap the fixed sheet under the header */
  return createPortal(
    <div className="co-sheet-wrap">
      <div className={"co-sheet co-sheet-" + state} role="dialog" aria-modal="true" aria-label="Payment">
        {state === "success" ? (
          <div className="co-result" key="ok">
            <span className="co-burst" aria-hidden="true">{Array.from({ length: 10 }, (_, k) => <i key={k} style={{ "--k": k }} />)}</span>
            <svg className="co-tick" viewBox="0 0 64 64" aria-hidden="true"><circle cx="32" cy="32" r="29" /><path d="M20 33l8 8 16-17" /></svg>
            <h3>{job.method === "cod" ? "Order placed" : "Payment successful"}</h3>
            <p>{job.method === "cod" ? `Pay ${inr(amount)} when your order arrives` : `${inr(amount)} paid`}</p>
          </div>
        ) : state === "failed" ? (
          <div className="co-result co-fail" key="fail">
            <svg className="co-cross" viewBox="0 0 64 64" aria-hidden="true"><circle cx="32" cy="32" r="29" /><path d="M23 23l18 18M41 23 23 41" /></svg>
            <h3>Payment failed</h3>
            <p>{error}</p>
            <small>If money was deducted, it will be refunded to the source within 3–5 working days.</small>
            <div className="co-row-center">
              <button className="co-ghost" onClick={onChangeMethod}>Change method</button>
              <button className="co-primary" onClick={onRetry}>Retry payment</button>
            </div>
          </div>
        ) : state === "otp" ? (
          <div className="co-otp-wrap" key="otp">
            <div className="co-bankbar"><Icon n="lock" size={14} />Secure verification · {job.cardLabel}</div>
            <h3>Enter OTP</h3>
            <p>Sent to the mobile number registered with your bank, ending ••••3210</p>
            <div className="co-otp-amt"><span>Amount</span><b>{inr(amount)}</b></div>
            <OtpBoxes value={otp} onChange={(v) => { setOtp(v); setOtpErr(""); }} disabled={otpBusy} shake={shake} />
            {otpErr ? <p className="co-error" key={otpErr + shake}>{otpErr}</p> : <p className="co-hint">Demo: any 6 digits (000000 shows a wrong OTP)</p>}
            <div className="co-row-between">
              <button className="co-link" disabled={resend > 0} onClick={() => setResend(30)}>{resend > 0 ? `Resend OTP in ${resend}s` : "Resend OTP"}</button>
              <button className="co-primary" disabled={otp.length < 6 || otpBusy} onClick={() => submitOtp(otp)}>{otpBusy ? <i className="co-spin co-spin-w" /> : "Verify & pay"}</button>
            </div>
            <button className="co-cancel" onClick={onCancel}>Cancel payment</button>
          </div>
        ) : job.method === "upi" ? (
          <div className="co-upi-wait" key="upi">
            <div className="co-phone" aria-hidden="true">
              <span className="co-phone-notch" />
              <span className="co-notif" style={{ "--tone": app?.tone || "#0a78ab" }}>
                <b>{app?.short || "UPI"}</b><span><strong>Payment request</strong>369 Mart · {inr(amount)}</span>
              </span>
              <span className="co-phone-pulse" />
            </div>
            <h3>Approve {inr(amount)} in {job.vpa && !job.upiApp ? "your UPI app" : app?.name || "your UPI app"}</h3>
            <p>{job.vpa ? <>Request sent to <b>{job.vpa}</b></> : "Open the app and approve the payment request"}</p>
            <CountdownRing secs={secs} total={300} />
            <p className="co-hint">Don't press back or close this page{job.vpa ? " · Demo: a UPI ID with “fail” is declined" : ""}</p>
            <button className="co-cancel" onClick={onCancel}>Cancel payment</button>
          </div>
        ) : job.method === "netbanking" ? (
          <div className="co-redirect" key="nb">
            <span className="co-bank-logo co-big" style={{ "--tone": bank?.tone }}>{bank?.short || "BANK"}</span>
            <h3>{redirect < 2 ? `Redirecting to ${bank?.name || "your bank"}` : "Waiting for your bank"}</h3>
            <p>Log in and authorise {inr(amount)} on your bank's secure page.</p>
            <div className="co-steps3">{["Connecting", "Secure page", "Authorising"].map((l, k) => <span key={l} className={k <= redirect ? "co-on" : ""}><i />{l}</span>)}</div>
            <p className="co-hint"><Icon n="lock" size={12} />256-bit encrypted</p>
          </div>
        ) : (
          <div className="co-placing" key="placing">
            <span className="co-bag" aria-hidden="true"><Icon n={job.method === "wallet" ? "wallet" : "bag"} size={34} /></span>
            <h3>{job.method === "wallet" ? "Paying from 369 Wallet" : "Placing your order"}</h3>
            <p>Confirming items with the store…</p>
            <span className="co-bar"><i /></span>
          </div>
        )}
      </div>
    </div>,
    document.querySelector(".hm-page") || document.body
  );
}

/* ---------------- page ---------------- */
export default function CheckoutPage({
  cart, byId, rules = CART_RULES, draft = {}, addresses, setAddresses, address, onSelectAddress,
  walletBalance = 0, onBack, onPlaced, ready = true,
}) {
  const coupon = draft.coupon || null;
  const bill = useMemo(() => computeBill({ cart, byId, rules, coupon }), [cart, byId, rules, coupon]);
  const slots = useSlots();
  const [step, setStep] = useState(address ? 2 : 1);
  const [slot, setSlot] = useState({ quick: "now", all: "std" });
  const [walletUse, setWalletUse] = useState(false);
  const [pay, setPay] = useState({
    method: draft.how === "cod" ? "cod" : "upi", upiApp: "gpay", useVpa: false, vpa: "", vpaName: "", vpaError: "",
    cardId: SAVED_CARDS[0]?.id || "new", savedCvv: "", cardNum: "", cardName: "", cardExp: "", cardCvv: "", saveCard: true, bank: "",
  });
  const [job, setJob] = useState(null);
  const [attempt, setAttempt] = useState(0);
  const [nudge, setNudge] = useState(0);
  const [summaryOpen, setSummaryOpen] = useState(false);
  useEffect(() => { if (!address && addresses.length === 0) setStep(1); }, [address, addresses.length]);

  const priority = bill.groups.all.length && slot.all === "pri" ? PRIORITY_FEE : 0;
  const gross = bill.total + priority;
  const walletUsed = walletUse ? Math.min(walletBalance, gross) : 0;
  const payable = gross - walletUsed;
  const wallet = { used: walletUsed, covers: walletUse && walletUsed >= gross, total: gross };
  const codAllowed = payable <= COD_LIMIT;
  useEffect(() => { if (pay.method === "cod" && !codAllowed) setPay((p) => ({ ...p, method: "upi" })); }, [codAllowed]); // eslint-disable-line

  const methodReady = (() => {
    if (wallet.covers) return true;
    if (pay.method === "upi") return pay.useVpa ? !!pay.vpaName : !!pay.upiApp;
    if (pay.method === "card") return pay.cardId === "new" ? luhn(pay.cardNum) && expiryOk(pay.cardExp) && pay.cardCvv.length >= 3 && pay.cardName.trim().length > 1 : pay.savedCvv.length >= 3;
    if (pay.method === "netbanking") return !!pay.bank;
    return pay.method === "cod";
  })();
  const hint = !methodReady && (pay.method === "upi" ? "Verify your UPI ID to continue" : pay.method === "card" ? (pay.cardId === "new" ? "Complete the card details" : "Enter the CVV") : pay.method === "netbanking" ? "Choose your bank" : "");

  const slotLabel = [
    bill.groups.quick.length ? slots.quick.find((s) => s.key === slot.quick)?.label : null,
    bill.groups.all.length ? slots.all.find((s) => s.key === slot.all)?.label : null,
  ].filter(Boolean).join(" · ");

  const startPay = () => {
    if (!methodReady) { setNudge((n) => n + 1); return; }
    const method = wallet.covers ? "wallet" : pay.method;
    const saved = SAVED_CARDS.find((c) => c.id === pay.cardId);
    const last4 = pay.cardId === "new" ? pay.cardNum.replace(/\D/g, "").slice(-4) : saved?.last4;
    setJob({
      method, upiApp: pay.useVpa ? null : pay.upiApp, vpa: pay.useVpa ? pay.vpa : "", bank: pay.bank,
      card: pay.cardId === "new" ? pay.cardNum : "0000" + (saved?.last4 || ""),
      cardLabel: `${BRAND_LABEL[pay.cardId === "new" ? cardBrand(pay.cardNum) : saved?.brand] || "Card"} •••• ${last4}`,
    });
    setAttempt((n) => n + 1);
  };

  const placed = (r) => {
    const mode = bill.groups.quick.length ? "quick" : "all";
    const method = job.method;
    const app = UPI_APPS.find((a) => a.key === job.upiApp);
    const payNote = method === "upi" ? (job.vpa || `${app?.name}`) : method === "card" ? job.cardLabel : method === "netbanking" ? BANKS.find((b) => b.key === job.bank)?.name : method === "wallet" ? "369 Wallet" : "Cash on delivery";
    const at = Date.now();
    const order = {
      id: newOrderId(mode), at, mode,
      placed: "Today, " + new Date(at).toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit" }),
      status: "placed",
      eta: bill.groups.quick.length && slot.quick === "now" ? "Arriving in 10–20 mins" : slotLabel,
      items: bill.lines.map((l) => [l.p.id, l.qty]),
      snap: Object.fromEntries(bill.lines.map((l) => [l.p.id, { name: l.p.name, price: l.p.price }])),
      total: gross,
      paid: payable, /* charged through the chosen method (cash on delivery: collected at the door) */
      walletUsed,
      pay: method === "cod" ? "Cash on delivery" : payNote,
      method, payNote, txn: r.txn, coupon: bill.couponValid ? coupon : null,
      bill: { items: bill.items, mrp: bill.mrp, fees: bill.fees + priority, couponOff: bill.couponOff, total: gross },
      address, slot: slotLabel, instructions: draft.instructions, whatsapp: draft.whatsapp,
    };
    onPlaced(order);
  };

  if (!ready) return <div className="co-page"><div className="co-skel"><span /><span /><span /></div></div>;

  if (!bill.count) {
    return (
      <div className="co-page">
        <div className="co-card co-empty">
          <Icon n="cart" size={36} />
          <h1>Nothing to check out</h1>
          <p>Your cart is empty. Add a few things and come back.</p>
          <button className="co-primary" onClick={onBack}>Back to shopping</button>
        </div>
      </div>
    );
  }

  const cta = step === 1
    ? { label: "Deliver here", disabled: !address, go: () => setStep(2) }
    : step === 2 ? { label: "Continue to payment", go: () => setStep(3) }
    : { label: wallet.covers ? "Pay with wallet" : pay.method === "cod" ? "Place order" : `Pay ${inr(payable)}`, go: startPay };

  return (
    <div className="co-page">
      <div className="co-titlebar">
        <button className="co-back" onClick={onBack} aria-label="Back to cart"><Icon n="left" size={20} /></button>
        <h1>Checkout</h1>
        <span className="co-secure"><Icon n="lock" size={13} />100% secure</span>
      </div>
      <Progress step={step} />

      {bill.blocked && (
        <div className="co-card co-warn"><Icon n="info" size={18} /><p>Your Quick items are below the {inr(rules.quick.minOrder)} minimum.</p><button className="co-link" onClick={onBack}>Edit cart</button></div>
      )}

      <div className="co-grid">
        <div className="co-main">
          <Step n={1} icon="pin" title="Delivery address" open={step === 1} done={!!address && step > 1}
            summary={address ? `${address.label} · ${address.line}${address.city ? ", " + address.city : ""}` : ""} onEdit={() => setStep(1)}>
            <AddressStep addresses={addresses} setAddresses={setAddresses} selected={address} onSelect={onSelectAddress} onContinue={() => setStep(2)} />
          </Step>
          <Step n={2} icon="clock" title="Delivery slot" open={step === 2} done={step > 2} summary={step > 2 ? slotLabel : ""} onEdit={() => setStep(2)}>
            <SlotStep bill={bill} slots={slots} slot={slot} setSlot={setSlot} onContinue={() => setStep(3)} />
          </Step>
          <Step n={3} icon="card" title="Payment" open={step === 3} done={false}>
            <div key={nudge} className={nudge ? "co-nudge" : ""}>
              <PaymentStep payable={payable} pay={pay} setPay={setPay} wallet={wallet} walletUse={walletUse} setWalletUse={setWalletUse} walletBal={walletBalance} codAllowed={codAllowed} />
            </div>
          </Step>
        </div>

        <aside className="co-side">
          <section className={"co-card co-summary" + (summaryOpen ? " co-open" : "")}>
            <button className="co-sum-head" onClick={() => setSummaryOpen((v) => !v)} aria-expanded={summaryOpen}>
              <span className="co-thumbs">{bill.lines.slice(0, 4).map((l, k) => <span key={l.p.id} style={{ "--k": k }}><Thumb p={l.p} /></span>)}</span>
              <span><b>Order summary</b><small>{bill.count} {bill.count === 1 ? "item" : "items"}</small></span>
              <Icon n="chev" size={18} className="co-chev" />
            </button>
            <div className="co-collapse"><div inert={!summaryOpen}>
              <ul className="co-lines">
                {bill.lines.map((l) => <li key={l.p.id}><span className="co-line-img"><Thumb p={l.p} /></span><span className="co-line-name">{l.p.name}<small>{l.qty} × {inr(l.p.price)}</small></span><b>{inr(l.p.price * l.qty)}</b></li>)}
              </ul>
            </div></div>
            <dl className="co-bill">
              <div><dt>MRP total</dt><dd><Amount value={bill.mrp} /></dd></div>
              {bill.mrp > bill.items && <div className="co-green"><dt>Product discount</dt><dd><Amount value={bill.mrp - bill.items} prefix="−" /></dd></div>}
              <div><dt>Delivery</dt><dd>{bill.fees ? <Amount value={bill.fees} /> : <span className="co-free">FREE</span>}</dd></div>
              {priority > 0 && <div className="co-rowin"><dt>Priority delivery</dt><dd>{inr(priority)}</dd></div>}
              {bill.couponOff > 0 && <div className="co-green"><dt>Coupon {coupon}</dt><dd><Amount value={bill.couponOff} prefix="−" /></dd></div>}
              {walletUsed > 0 && <div className="co-green co-rowin"><dt>369 Wallet</dt><dd><Amount value={walletUsed} prefix="−" /></dd></div>}
              <div className="co-total"><dt>{pay.method === "cod" && !wallet.covers ? "To pay on delivery" : "To pay"}</dt><dd><Amount value={payable} /></dd></div>
            </dl>
            {bill.saved > 0 && <p className="co-saving" key={bill.saved}><Icon n="gift" size={15} />You're saving {inr(bill.saved)} on this order</p>}
            <button className={"co-primary co-paybtn" + (step === 3 && !methodReady ? " co-soft" : "")} disabled={step === 1 && !address || bill.blocked || !!job} onClick={cta.go}>
              {job ? <i className="co-spin co-spin-w" /> : <>{step === 3 && <Icon n="lock" size={15} />}{cta.label}</>}
            </button>
            {step === 3 && hint && <p className="co-hintline" key={hint}>{hint}</p>}
            {COUPONS.length > 0 && !coupon && <p className="co-muted co-small">Have a coupon? <button className="co-link" onClick={onBack}>Apply it in the cart</button></p>}
            <p className="co-trust"><Icon n="shield" size={14} />Payments are encrypted and processed by a PCI DSS compliant gateway.</p>
          </section>
        </aside>
      </div>

      <div className="co-mbar">
        <div><small>{step === 3 ? "To pay" : "Total"}</small><Amount value={step === 3 ? payable : gross} /></div>
        <button className="co-primary" disabled={(step === 1 && !address) || bill.blocked || !!job} onClick={cta.go}>{job ? <i className="co-spin co-spin-w" /> : cta.label}</button>
      </div>

      {job && (
        <PaySheet key={attempt} job={job} amount={payable}
          onDone={(r) => placed(r)}
          onCancel={() => setJob(null)}
          onRetry={() => { setJob(null); setTimeout(startPay, 60); }}
          onChangeMethod={() => { setJob(null); setStep(3); }} />
      )}
    </div>
  );
}
