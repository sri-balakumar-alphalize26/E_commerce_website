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
import { Icon, Thumb, money } from "./shared";
import { Amount, computeBill, useBill, useRules } from "./Cart";
import { useRemote } from "./accountStore";
import { BANKS, BRAND_LABEL, UPI_APPS, newOrderId } from "./payment";
import { api } from "@/lib/api";
import { useAction, useResource } from "@/lib/useFetch";

const PRIORITY_FEE = 49;

/* The cart collects these as toggles and a note; the order keeps one line of
   text, because that is what gets printed on a picking slip. */
const INSTRUCTION_WORDS = { nocall: "Avoid calling", nobell: "Don't ring the bell", pet: "Pet at home" };
function instructionLine(instructions) {
  if (!instructions || typeof instructions !== "object") return instructions || "";
  const said = Object.entries(INSTRUCTION_WORDS).filter(([k]) => instructions[k]).map(([, w]) => w);
  const note = (instructions.note || "").trim();
  return [...said, note].filter(Boolean).join(" · ");
}
const reduced = () => typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

/* ---------------- slots ----------------

   The windows come from the shop, where an operator sets them: what each chip
   says, which hours it covers, what it costs and how many orders it can take.
   `/slots` hands back exactly the shape this page draws, already filtered to
   the ones open right now - a "Today, 6 - 8 PM" is gone from the list after
   six, and a full window stops being offered, neither of which a clock in the
   browser can know.

   The clock version is kept as the fallback, for the first paint and for a
   shop that cannot be reached. It is the wrong answer in the small ways just
   listed, but an empty slot step is the wrong answer in every way. */
function useClockSlots() {
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

function useSlots() {
  const { data } = useResource("/slots");
  const clock = useClockSlots();
  return useMemo(() => {
    /* Each storefront falls back on its own. A shop with slots for Quick and
       none for Express should not have its Quick list thrown away too. */
    const quick = data?.quick?.length ? data.quick : clock.quick;
    const all = data?.all?.length ? data.all : clock.all;
    return { quick, all };
  }, [data, clock]);
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
function AddressStep({ addresses, onAddAddress, selected, onSelect, onContinue, phoneHint }) {
  const [adding, setAdding] = useState(!addresses.length);
  const [d, setD] = useState({ label: "Home", name: "", phone: "", line: "", city: "", pin: "" });
  const [err, setErr] = useState({});
  const [saving, setSaving] = useState(false);
  const save = async (e) => {
    e.preventDefault();
    const x = {};
    if (!d.name.trim()) x.name = "Enter the receiver's name";
    /* The shop knows what a phone number looks like where it trades, and sends
       the rule with the address book. A hard-coded 10-digit Indian number was
       rejecting numbers the shop itself would have accepted. */
    const len = phoneHint?.length || 10;
    if (!new RegExp("^\\d{" + len + "}$").test(d.phone)) x.phone = `Enter a ${len}-digit mobile number`;
    if (d.line.trim().length < 6) x.line = "Add house / flat and street";
    if (!d.city.trim()) x.city = "Enter city";
    if (!/^\d{6}$/.test(d.pin)) x.pin = "6-digit pincode";
    setErr(x);
    if (Object.keys(x).length) return;
    setSaving(true);
    const a = await onAddAddress({
      label: d.label, name: d.name.trim(), phone: d.phone,
      line: d.line.trim(), city: `${d.city.trim()} ${d.pin}`,
    });
    setSaving(false);
    if (!a) { setErr({ line: "Could not save that address. Try again." }); return; }
    onSelect(a); setAdding(false);
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
                  <small>{s.fee ? `+${money(s.fee)}` : g === "quick" && s.key === "now" ? "Fastest" : "Free"}</small>
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
function PaymentStep({ payable, pay, setPay, wallet, walletUse, setWalletUse, walletBal, offered, codLimit, cards = [], upis = [] }) {
  const set = (patch) => setPay((p) => ({ ...p, ...patch }));

  /* Only what the shop can actually take. It used to offer all four and find
     out at the last step - the worst possible moment to learn that a way of
     paying is not switched on. */
  const ALL = [
    { key: "upi", icon: "upi", title: "UPI", sub: "Approve the request in your UPI app" },
    { key: "card", icon: "card", title: "Credit / debit card", sub: "Verified on your bank's own page" },
    { key: "netbanking", icon: "bank", title: "Net banking", sub: "Authorise on your bank's page" },
    { key: "cod", icon: "cash", title: "Cash on delivery", sub: codLimit ? `Pay at your door · up to ${money(codLimit)}` : "Pay at your door" },
  ];
  const methods = ALL.filter((m) => offered.includes(m.key));

  return (
    <>
      <label className={"co-wallet" + (walletUse ? " co-on" : "")}>
        <span className="co-wallet-ic"><Icon n="wallet" size={20} /></span>
        <span className="co-wallet-txt"><b>369 Wallet</b><small>Balance <Amount value={walletUse ? Math.max(0, walletBal - wallet.used) : walletBal} /></small></span>
        {walletUse && wallet.used > 0 && <em key={wallet.used} className="co-wallet-used">−{money(wallet.used)}</em>}
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
                      {upis.length > 0 && (
                        <div className="co-saved co-savedupi">
                          {upis.map((u) => {
                            const onU = pay.useVpa && pay.vpa === u.vpa;
                            return (
                              <button key={u.id} className={"co-savedcard" + (onU ? " co-on" : "")} onClick={() => set({ useVpa: true, vpa: u.vpa, vpaName: u.name, vpaError: "" })} tabIndex={on ? 0 : -1}>
                                <Radio on={onU} /><span className="co-brandtag"><Icon n="upi" size={14} /></span>
                                <span><b>{u.vpa}</b><small>Saved · verified as {u.name}</small></span>
                              </button>
                            );
                          })}
                        </div>
                      )}
                      <div className="co-apps">
                        {UPI_APPS.map((a, k) => (
                          <button key={a.key} className={"co-app" + (pay.upiApp === a.key && !pay.useVpa ? " co-on" : "")} style={{ "--k": k, "--tone": a.tone }} onClick={() => set({ upiApp: a.key, useVpa: false })} tabIndex={on ? 0 : -1}>
                            <span className="co-app-logo">{a.short}</span><small>{a.name}</small>
                          </button>
                        ))}
                      </div>
                      <p className="co-codnote"><Icon n="info" size={16} />Add a UPI ID in your account to pay with it here. Otherwise pick an app and approve the request when it arrives.</p>
                    </>
                  )}

                  {m.key === "card" && (
                    <>
                      <div className="co-saved">
                        {cards.map((c) => (
                          <button key={c.id} className={"co-savedcard" + (pay.cardId === c.id ? " co-on" : "")} onClick={() => set({ cardId: c.id })} tabIndex={on ? 0 : -1}>
                            <Radio on={pay.cardId === c.id} />
                            <span className={"co-brandtag co-b-" + c.brand}>{BRAND_LABEL[c.brand]}</span>
                            <span><b>•••• {c.last4}</b><small>{c.bank} · expires {c.exp}</small></span>
                          </button>
                        ))}
                      </div>
                      {/* The number is typed on the provider's own field and
                          tokenised there; /pay refuses one posted to us. */}
                      <p className="co-codnote"><Icon n="lock" size={16} />
                        {cards.length
                          ? "You'll confirm this on your bank's secure page."
                          : "No saved card yet. You'll enter it on your bank's secure page and can save it for next time."}
                      </p>
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

function PaySheet({ job, amount, onDone, onFail, onCancel, onRetry, onChangeMethod }) {
  const [state, setState] = useState("working"); // working | success | failed
  const [secs, setSecs] = useState(300);
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

  /* The payment is the shop's to settle: it was started before this sheet
     opened, and all this does is ask how it is going. A UPI approval happens
     in another app entirely and a bank page in another tab, so there is
     nothing here to await - only a state to watch until it stops being
     pending. */
  useEffect(() => {
    let stopped = false;
    const tick = job.method === "upi" ? setInterval(() => setSecs((x) => Math.max(0, x - 1)), 1000)
      : job.method === "netbanking" ? setInterval(() => setRedirect((n) => Math.min(3, n + 1)), 800)
      : null;
    const poll = async () => {
      if (stopped || !alive.current) return;
      try {
        const r = await api(`/payment/status/${encodeURIComponent(job.reference)}`, { raw: true, fresh: true });
        if (stopped || !alive.current) return;
        if (r?.state === "pending") return;
        finish(r || { ok: false });
        stopped = true;
      } catch (e) {
        /* A dropped connection is not a declined payment - keep asking. */
      }
    };
    poll();
    const id = setInterval(poll, 2000);
    return () => { stopped = true; clearInterval(id); if (tick) clearInterval(tick); };
  }, []); // eslint-disable-line

  const app = UPI_APPS.find((a) => a.key === job.upiApp);
  const bank = BANKS.find((b) => b.key === job.bank);
  const giveUp = async () => {
    try { await api(`/payment/${encodeURIComponent(job.reference)}/cancel`, { method: "POST", raw: true }); } catch (e) {}
    onCancel?.();
  };

  /* portalled to .hm-page: the animated page wrapper would otherwise trap the fixed sheet under the header */
  return createPortal(
    <div className="co-sheet-wrap">
      <div className={"co-sheet co-sheet-" + state} role="dialog" aria-modal="true" aria-label="Payment">
        {state === "success" ? (
          <div className="co-result" key="ok">
            <span className="co-burst" aria-hidden="true">{Array.from({ length: 10 }, (_, k) => <i key={k} style={{ "--k": k }} />)}</span>
            <svg className="co-tick" viewBox="0 0 64 64" aria-hidden="true"><circle cx="32" cy="32" r="29" /><path d="M20 33l8 8 16-17" /></svg>
            <h3>{job.method === "cod" ? "Order placed" : "Payment successful"}</h3>
            <p>{job.method === "cod" ? `Pay ${money(amount)} when your order arrives` : `${money(amount)} paid`}</p>
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
        ) : job.method === "upi" ? (
          <div className="co-upi-wait" key="upi">
            <div className="co-phone" aria-hidden="true">
              <span className="co-phone-notch" />
              <span className="co-notif" style={{ "--tone": app?.tone || "#0a78ab" }}>
                <b>{app?.short || "UPI"}</b><span><strong>Payment request</strong>369 Mart · {money(amount)}</span>
              </span>
              <span className="co-phone-pulse" />
            </div>
            <h3>Approve {money(amount)} in {job.vpa && !job.upiApp ? "your UPI app" : app?.name || "your UPI app"}</h3>
            <p>{job.vpa ? <>Request sent to <b>{job.vpa}</b></> : "Open the app and approve the payment request"}</p>
            <CountdownRing secs={secs} total={300} />
            <p className="co-hint">Don't press back or close this page</p>
            <button className="co-cancel" onClick={giveUp}>Cancel payment</button>
          </div>
        ) : job.method === "netbanking" ? (
          <div className="co-redirect" key="nb">
            <span className="co-bank-logo co-big" style={{ "--tone": bank?.tone }}>{bank?.short || "BANK"}</span>
            <h3>{redirect < 2 ? `Redirecting to ${bank?.name || "your bank"}` : "Waiting for your bank"}</h3>
            <p>Log in and authorise {money(amount)} on your bank's secure page.</p>
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
  cart, byId, draft = {}, addresses, onAddAddress, address, onSelectAddress, phoneHint,
  walletBalance = 0, onBack, onPlaced, ready = true,
}) {
  const coupon = draft.coupon || null;
  const { rules, coupons } = useRules();
  const slots = useSlots();
  const [step, setStep] = useState(address ? 2 : 1);
  const [slot, setSlot] = useState({ quick: "now", all: "std" });
  /* The extra a slot costs is a line on the bill, so the shop adds it, not
     this page: it is handed the number and works out the total. Which number
     comes from the chosen chip, which is the operator's to set - not a
     constant in this file that nobody outside it could change. */
  const shape = useMemo(() => computeBill({ cart, byId }), [cart, byId]);
  const chosen = slots.all.find((s) => s.key === slot.all);
  const priority = shape.groups.all.length ? Number(chosen?.fee) || 0 : 0;
  const bill = useBill({ cart, byId, rules, coupon, slotFee: priority });
  /* The shop's slots arrive after the first paint, and the keys it offers are
     the operator's, not this file's. Keep the pick on a chip that exists, or
     "std" would stay selected against a list that no longer has it and the
     step would show nothing chosen. */
  useEffect(() => {
    setSlot((s) => ({
      quick: slots.quick.some((c) => c.key === s.quick) ? s.quick : slots.quick[0]?.key || s.quick,
      all: slots.all.some((c) => c.key === s.all) ? s.all : slots.all[0]?.key || s.all,
    }));
  }, [slots]);
  const [walletUse, setWalletUse] = useState(false);
  const [pay, setPay] = useState({
    method: "", upiApp: "gpay", useVpa: false, vpa: "", cardId: "", bank: "",
  });
  const { data: methods, reload: reloadMethods } = useRemote("/payment/methods");
  const savedPay = useMemo(() => ({ cards: methods?.cards || [], upis: methods?.upis || [] }), [methods]);
  const cards = useMemo(() => [...savedPay.cards].sort((a, b) => !!b.default - !!a.default), [savedPay.cards]);
  useEffect(() => { /* saved cards load after mount: keep the pick valid */
    setPay((p) => (p.cardId === "new" || cards.some((c) => c.id === p.cardId) ? p : { ...p, cardId: cards[0]?.id || "new" }));
  }, [cards]);
  const [job, setJob] = useState(null);
  const place = useAction();
  const [attempt, setAttempt] = useState(0);
  const [nudge, setNudge] = useState(0);
  const [summaryOpen, setSummaryOpen] = useState(false);
  useEffect(() => { if (!address && addresses.length === 0) setStep(1); }, [address, addresses.length]);

  const gross = bill.total;
  const walletUsed = walletUse ? Math.min(walletBalance, gross) : 0;
  const payable = gross - walletUsed;
  const wallet = { used: walletUsed, covers: walletUse && walletUsed >= gross, total: gross };
  const slotLabel = [
    bill.groups.quick.length ? slots.quick.find((s) => s.key === slot.quick)?.label : null,
    bill.groups.all.length ? slots.all.find((s) => s.key === slot.all)?.label : null,
  ].filter(Boolean).join(" · ");

  /* The order is written before a way of paying is chosen, because whether
     cash is allowed is a question about the order - Odoo asks the order's own
     delivery method - and there is no honest way to answer it for a basket
     that does not exist yet. It is a draft until it is paid for: it is in
     nobody's list and nobody has been asked to pack it, and coming back to
     change the slot rewrites it rather than making a second one.

     The reference is the app's, and that is what makes paying twice safe. */
  const ref = useRef(null);
  const [ordered, setOrdered] = useState(null);
  const { data: options } = useResource(`/payment/options?amount=${Math.round(payable)}&order_ref=${encodeURIComponent(ordered || "")}`, { enabled: !!ordered });

  /* Which ways of paying the shop can take for this amount, from the shop.
     A ceiling is part of it - cash on delivery drops off a large basket by
     itself rather than by a constant kept here. */
  const offered = useMemo(() => options?.methods || [], [options]);
  useEffect(() => {
    if (!offered.length) return;
    setPay((p) => (offered.includes(p.method) ? p : { ...p, method: draft.how === "cod" && offered.includes("cod") ? "cod" : offered[0] }));
  }, [offered]); // eslint-disable-line

  const methodReady = (() => {
    if (wallet.covers) return true;
    if (!offered.includes(pay.method)) return false;
    if (pay.method === "netbanking") return !!pay.bank;
    return true;
  })();
  const hint = !methodReady && (offered.length
    ? (pay.method === "netbanking" ? "Choose your bank" : "Choose how you'd like to pay")
    : "No way of paying is switched on yet — please contact the shop.");


  const draftOrder = () => {
    if (!ref.current) ref.current = newOrderId(bill.groups.quick.length ? "quick" : "all");
    return place.run(async () => {
      await api("/orders", {
        method: "POST",
        body: {
          ref: ref.current,
          items: cart,
          address_id: address?.id,
          coupon: coupon || "",
          mode: bill.groups.quick.length ? "quick" : "all",
          slot_key: bill.groups.all.length ? slot.all : slot.quick,
          slot: slotLabel,
          eta: bill.groups.quick.length && slot.quick === "now" ? "Arriving in 10–20 mins" : slotLabel,
          instructions: instructionLine(draft.instructions),
          whatsapp: !!draft.whatsapp,
        },
      });
      setOrdered(ref.current);
      return ref.current;
    });
  };

  /* The amount is not sent. The shop prices the basket it already holds and
     debits the wallet itself before asking a gateway for the rest - the app
     used to write the order and then debit, which made a crash between the
     two lines a free order, and let the browser claim a balance it did not
     have to drag the remainder under the cash-on-delivery ceiling. */
  const startPay = () => {
    if (!methodReady) { setNudge((n) => n + 1); return; }
    const method = wallet.covers ? "wallet" : pay.method;
    const saved = cards.find((c) => c.id === pay.cardId);
    const token = method === "card" ? saved : method === "upi" && pay.useVpa ? upis.find((u) => u.vpa === pay.vpa) : null;

    place.run(async () => {
      const started = await api("/payment/pay", {
        method: "POST",
        body: {
          order_ref: ref.current,
          method,
          wallet_use: walletUse || method === "wallet",
          token_id: token ? Number(token.id) : undefined,
        },
      });
      setJob({
        method, reference: started.reference,
        upiApp: pay.useVpa ? null : pay.upiApp, vpa: pay.useVpa ? pay.vpa : "", bank: pay.bank,
        cardLabel: saved ? `${BRAND_LABEL[saved.brand] || "Card"} •••• ${saved.last4}` : "",
      });
      setAttempt((n) => n + 1);
      return true;
    });
  };

  /* The receipt is the order the shop wrote, read back. Building one here
     from what the page happened to be holding is how a receipt ends up
     disagreeing with the invoice. */
  const placed = async () => {
    const answer = await api(`/orders/${encodeURIComponent(ref.current)}`, { raw: true, fresh: true });
    api.invalidate("/orders");
    if (answer?.order) onPlaced(answer.order);
    ref.current = null;
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
    : step === 2 ? { label: "Continue to payment", go: async () => { if (await draftOrder()) setStep(3); } }
    : { label: wallet.covers ? "Pay with wallet" : pay.method === "cod" ? "Place order" : `Pay ${money(payable)}`, go: startPay };

  return (
    <div className="co-page">
      <div className="co-titlebar">
        <button className="co-back" onClick={onBack} aria-label="Back to cart"><Icon n="left" size={20} /></button>
        <h1>Checkout</h1>
        <span className="co-secure"><Icon n="lock" size={13} />100% secure</span>
      </div>
      <Progress step={step} />

      {bill.blocked && (
        <div className="co-card co-warn"><Icon n="info" size={18} /><p>Your Quick items are below the {money(rules.quick.minOrder)} minimum.</p><button className="co-link" onClick={onBack}>Edit cart</button></div>
      )}

      <div className="co-grid">
        <div className="co-main">
          <Step n={1} icon="pin" title="Delivery address" open={step === 1} done={!!address && step > 1}
            summary={address ? `${address.label} · ${address.line}${address.city ? ", " + address.city : ""}` : ""} onEdit={() => setStep(1)}>
            <AddressStep addresses={addresses} onAddAddress={onAddAddress} selected={address} onSelect={onSelectAddress}
              onContinue={() => setStep(2)} phoneHint={phoneHint} />
          </Step>
          <Step n={2} icon="clock" title="Delivery slot" open={step === 2} done={step > 2} summary={step > 2 ? slotLabel : ""} onEdit={() => setStep(2)}>
            <SlotStep bill={bill} slots={slots} slot={slot} setSlot={setSlot} onContinue={async () => { if (await draftOrder()) setStep(3); }} />
          </Step>
          <Step n={3} icon="card" title="Payment" open={step === 3} done={false}>
            <div key={nudge} className={nudge ? "co-nudge" : ""}>
              <PaymentStep payable={payable} pay={pay} setPay={setPay} wallet={wallet} walletUse={walletUse} setWalletUse={setWalletUse} walletBal={walletBalance} offered={offered} codLimit={options?.codLimit || 0} cards={cards} upis={savedPay.upis} />
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
                {bill.lines.map((l) => <li key={l.p.id}><span className="co-line-img"><Thumb p={l.p} /></span><span className="co-line-name">{l.p.name}<small>{l.qty} × {money(l.p.price)}</small></span><b>{money(l.p.price * l.qty)}</b></li>)}
              </ul>
            </div></div>
            <dl className="co-bill">
              <div><dt>MRP total</dt><dd><Amount value={bill.mrp} /></dd></div>
              {bill.mrp > bill.items && <div className="co-green"><dt>Product discount</dt><dd><Amount value={bill.mrp - bill.items} prefix="−" /></dd></div>}
              <div><dt>Delivery</dt><dd>{bill.fees - priority > 0 ? <Amount value={bill.fees - priority} /> : <span className="co-free">FREE</span>}</dd></div>
              {priority > 0 && <div className="co-rowin"><dt>Priority delivery</dt><dd>{money(priority)}</dd></div>}
              {bill.couponOff > 0 && <div className="co-green"><dt>Coupon {coupon}</dt><dd><Amount value={bill.couponOff} prefix="−" /></dd></div>}
              {walletUsed > 0 && <div className="co-green co-rowin"><dt>369 Wallet</dt><dd><Amount value={walletUsed} prefix="−" /></dd></div>}
              <div className="co-total"><dt>{pay.method === "cod" && !wallet.covers ? "To pay on delivery" : "To pay"}</dt><dd><Amount value={payable} /></dd></div>
            </dl>
            {bill.saved > 0 && <p className="co-saving" key={bill.saved}><Icon n="gift" size={15} />You're saving {money(bill.saved)} on this order</p>}
            <button className={"co-primary co-paybtn" + (step === 3 && !methodReady ? " co-soft" : "")} disabled={step === 1 && !address || bill.blocked || !bill.priced || !!job || place.busy} onClick={cta.go}>
              {job ? <i className="co-spin co-spin-w" /> : <>{step === 3 && <Icon n="lock" size={15} />}{cta.label}</>}
            </button>
            {step === 3 && hint && <p className="co-hintline" key={hint}>{hint}</p>}
            {coupons.length > 0 && !coupon && <p className="co-muted co-small">Have a coupon? <button className="co-link" onClick={onBack}>Apply it in the cart</button></p>}
            <p className="co-trust"><Icon n="shield" size={14} />Payments are encrypted and processed by a PCI DSS compliant gateway.</p>
          </section>
        </aside>
      </div>

      <div className="co-mbar">
        <div><small>{step === 3 ? "To pay" : "Total"}</small><Amount value={step === 3 ? payable : gross} /></div>
        <button className="co-primary" disabled={(step === 1 && !address) || bill.blocked || !bill.priced || !!job || place.busy} onClick={cta.go}>{job || place.busy ? <i className="co-spin co-spin-w" /> : cta.label}</button>
      </div>

      {job && (
        <PaySheet key={attempt} job={job} amount={payable}
          onDone={() => placed()}
          onCancel={() => setJob(null)}
          onRetry={() => { setJob(null); setTimeout(startPay, 60); }}
          onChangeMethod={() => { setJob(null); setStep(3); }} />
      )}
    </div>
  );
}
