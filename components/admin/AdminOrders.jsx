"use client";
/* ==========================================================================
   369 Mart admin — Orders

   The screen a store manager keeps open all morning. It is built around one
   question — what do I pack next — rather than around listing orders, so:

   * it opens on "Needs me", oldest first, because the order that has waited
     longest is the one to act on and it belongs at the top;
   * every row carries its own next-step button, already labelled, so the
     common action costs one click and never opens the drawer;
   * the tiles along the top are the filters, not decoration.

   Nothing here knows the order of the steps. A quick order is packed next and
   an express one is shipped next, and the server says which and what the
   button is called (`row.next`). A second copy of that ladder in the browser
   is a second thing to get wrong, and the model would refuse the write anyway.

   Every write goes to the shop and then re-reads. Nothing is patched locally
   to look like it worked: the next state and the lateness are the server's to
   decide, and guessing them is how a panel starts lying.
   ========================================================================== */
import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { api } from "@/lib/api";
import { money } from "@/lib/money";
import { useAction, useResource } from "@/lib/useFetch";
import { Avatar, Confirm, Drawer, Empty, Icon, Pill, Search, Select, Tabs } from "./AdminUI";
import { clock, dateShort, dateTime, dueIn, overdueBy, since } from "./format";

/* The shop's own words, not a third dialect. These are the values of
   `mart369_state` on sale.order; the console used to run on new / packing /
   ready, which existed nowhere on the server. */
const STATUS = {
  placed: { label: "Placed", tone: "blue" },
  packed: { label: "Packed", tone: "amber" },
  shipped: { label: "Shipped", tone: "violet" },
  out: { label: "Out for delivery", tone: "orange" },
  delivered: { label: "Delivered", tone: "green" },
  cancelled: { label: "Cancelled", tone: "red" },
};

/* Tab key -> [label, which count to badge it with]. `needs` is the default and
   the only one that is a question rather than a filter. */
/* The states an order is still being worked in - what the countdown is for. */
const LIVE = ["placed", "packed", "shipped", "out"];
const TABS = [
  ["needs", "Needs me", "needs"],
  ["all", "All", null],
  ["delivered", "Delivered", null],
  ["returns", "Returns", "returns"],
  ["cancelled", "Cancelled", null],
];

/* The five tiles. Each one sets the tab, so the strip navigates. */
const TILES = [
  { tab: "placed", label: "To pack", icon: "box", tone: "#0a78ab" },
  { tab: "packing", label: "Ready to send", icon: "layers", tone: "#f7931e" },
  { tab: "out", label: "Out for delivery", icon: "truck", tone: "#7b5cd6" },
  { tab: "late", label: "Late", icon: "clock", tone: "#c2410c", warn: true },
  { tab: "cash", label: "Cash to collect", icon: "cash", tone: "#1a7f3c", amount: true },
];

const PAGE = 20;

/* "Needs me", grouped by what you do next - the Odoo desk groups the same. */
const NEXT_GROUPS = [
  { key: "pack", label: "To pack", states: ["placed"] },
  { key: "send", label: "Ready to send", states: ["packed", "shipped"] },
  { key: "out", label: "Out for delivery", states: ["out"] },
];
const groupRows = (tab, rows) => {
  if (tab !== "needs") return [{ key: "all", label: "", rows }];
  const out = NEXT_GROUPS.map((g) => ({ ...g, rows: rows.filter((r) => g.states.includes(r.state)) })).filter((g) => g.rows.length);
  const rest = rows.filter((r) => !NEXT_GROUPS.some((g) => g.states.includes(r.state)));
  if (rest.length) out.push({ key: "other", label: "Other", rows: rest });
  return out;
};
/* Payment in plain words: is the money in, or still to collect? */
const PAID_BY = { upi: "UPI", card: "card", netbanking: "net banking", wallet: "369 Wallet" };
const payText = (o) => {
  if (o.method === "cod") {
    if (o.state === "delivered") return "Cash collected";
    return o.state === "cancelled" ? "Cash on delivery" : "Cash on delivery — collect at the door";
  }
  const how = PAID_BY[o.method] || o.payNote || o.method;
  return how ? `Paid by ${how}` : "Paid";
};
const ROW_TONES = ["grey", "red", "orange", "amber", "blue", "violet", "green", "blue", "red", "violet", "green", "orange"];
const modeLabel = (m) => (m === "quick" ? "Quick" : "Express");

function Tiles({ counts, cashDue, tab, onPick }) {
  return (
    <div className="ad-stats ad-order-tiles">
      {TILES.map((t, i) => {
        const n = counts?.[t.tab] ?? 0;
        return (
          <button key={t.tab} type="button" style={{ "--i": i }}
            className={"ad-stat ad-stat-btn" + (tab === t.tab ? " ad-stat-on" : "") + (t.warn && n > 0 ? " ad-stat-warn" : "")}
            aria-pressed={tab === t.tab} onClick={() => onPick(t.tab)}>
            <header>
              <span className="ad-stat-ic" style={{ "--tone": t.tone }}><Icon n={t.icon} size={18} /></span>
              {t.label}
            </header>
            <b>{t.amount ? cashDue || "—" : n}</b>
            <div className="ad-stat-foot">
              <small>{t.amount ? `${n} order${n === 1 ? "" : "s"}` : "Tap to filter"}</small>
            </div>
          </button>
        );
      })}
    </div>
  );
}

/* One line of the timeline, drawn on the ladder the order is really on -
   `flow` comes from the server so a quick order shows Packed where an express
   one shows Shipped, rather than the screen picking from `mode`. */
function Timeline({ o }) {
  const stamped = Object.fromEntries((o.timeline || []).map((s) => [s.state, s]));
  const reached = o.flow.filter((k) => stamped[k]).length;
  return (
    <ol className="ad-timeline">
      {o.flow.map((k, i) => {
        const s = stamped[k];
        const now = i === reached - 1 && o.state !== "delivered" && o.state !== "cancelled";
        return (
          <li key={k} className={(s ? "ad-done" : "") + (now ? " ad-now" : "")} style={{ "--i": i }}>
            <i>{s ? <Icon n="check" size={11} /> : null}</i>
            <span><b>{STATUS[k].label}</b><small>{s ? clock(s.at) : "Pending"}</small></span>
          </li>
        );
      })}
      {stamped.cancelled && (
        <li className="ad-done ad-cancelled" style={{ "--i": 1 }}>
          <i><Icon n="x" size={11} /></i>
          <span><b>Cancelled</b><small>{stamped.cancelled.note || "By store"}</small></span>
        </li>
      )}
    </ol>
  );
}

/* ---- the order in plain words (the Odoo desk says the same) ---- */
const statusLine = (o) => {
  if (o.state === "cancelled") return "Cancelled.";
  if (o.state === "delivered") return "Delivered.";
  const promised = o.dueAt ? clock(o.dueAt) : "";
  if (o.late) return promised ? `${overdueBy(o.dueAt)} — it was promised by ${promised}.` : `${overdueBy(o.dueAt)}.`;
  return promised ? `On time — ${dueIn(o.dueAt)} (promised by ${promised}).` : "On time.";
};
const payLine = (o) => {
  const total = money(o.bill.total, o.currency);
  if (o.method === "cod") {
    return o.state === "delivered" ? "Cash on delivery — collected at the door."
      : o.state === "cancelled" ? "Cash on delivery — nothing to collect."
      : `Cash on delivery — collect ${total} at the door.`;
  }
  const how = o.payNote || o.method || "Paid online";
  return o.txn ? `${how} — paid ${total} (ref ${o.txn}).` : `${how} — paid ${total}.`;
};
const riskLine = (r) => [
  r?.cancelledByCustomer && `${r.cancelledByCustomer} cancelled by them`,
  r?.refused && `${r.refused} refused at the door`,
  r?.returned && `${r.returned} returned`,
  r?.codOff && "cash on delivery is off for them",
].filter(Boolean).join(" · ");
const TAG_TONES = ["grey", "red", "orange", "amber", "blue", "violet", "green", "blue", "red", "violet", "green", "orange"];
const addrLines = (a) => {
  if (!a) return [];
  const near = a.landmark && !/^(near|opp|opposite|behind|beside|next to)\b/i.test(a.landmark) ? "near " + a.landmark : a.landmark;
  const place = a.town ? `${a.town}${a.state ? ", " + a.state : ""}${a.pin ? " " + a.pin : ""}` : [a.city, a.state].filter(Boolean).join(", ");
  return [a.line, [a.area, near].filter(Boolean).join(", "), place].filter(Boolean);
};

/* The team's own notes on this order, signed; you change only your own. */
function OrderNotes({ ref_, notes, onSaved }) {
  const [text, setText] = useState("");
  const [editing, setEditing] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const run = async (path, opts, after) => {
    setBusy(true); setError("");
    try { const r = await api(path, opts); after?.(); onSaved(r.notes || []); }
    catch (e) { setError(e.message || "That did not work."); } finally { setBusy(false); }
  };
  const base = `/admin/orders/${encodeURIComponent(ref_)}/notes`;
  return (
    <section className="ad-dsec">
      <h4><Icon n="pen" size={14} />Staff notes</h4>
      {error && <p className="ad-form-error" role="alert">{error}</p>}
      <div className="ad-cust-note-new">
        <textarea rows={2} maxLength={1000} value={text} placeholder="e.g. Called, no answer — gate is locked"
          onChange={(e) => setText(e.target.value)} />
        <button className="ad-btn ad-primary" disabled={busy || !text.trim()}
          onClick={() => run(base, { method: "POST", body: { text: text.trim() } }, () => setText(""))}>Add</button>
      </div>
      {!!notes.length && (
        <ul className="ad-cust-notes">
          {notes.map((n) => (
            <li key={n.id}>
              {editing?.id === n.id ? (
                <>
                  <textarea className="ad-cust-note-edit" rows={2} maxLength={1000} autoFocus value={editing.text}
                    onChange={(e) => setEditing({ id: n.id, text: e.target.value })} />
                  <span className="ad-cust-note-edit-act">
                    <button className="ad-btn ad-sm" onClick={() => setEditing(null)}>Cancel</button>
                    <button className="ad-btn ad-sm ad-primary" disabled={busy || !editing.text.trim()}
                      onClick={() => run(`${base}/${n.id}`, { method: "PATCH", body: { text: editing.text.trim() } }, () => setEditing(null))}>Save</button>
                  </span>
                </>
              ) : <p>{n.text}</p>}
              <small>
                {n.author} · {n.at ? since(n.at) : ""}
                {n.mine && editing?.id !== n.id && (
                  <button type="button" className="ad-cust-note-pen" aria-label="Edit note" disabled={busy}
                    onClick={() => setEditing({ id: n.id, text: n.text })}><Icon n="pen" size={13} /></button>
                )}
                {n.mine && (
                  <button type="button" aria-label="Delete note" disabled={busy}
                    onClick={() => run(`${base}/${n.id}`, { method: "DELETE" })}><Icon n="trash" size={13} /></button>
                )}
              </small>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function OrderDrawer({ ref_, onClose, onAdvance, onCancel, onChanged, reasons, busy, flash, onOpenCustomer, onOpenTicket }) {
  const { data, loading, error, reload } = useResource(`/admin/orders/${encodeURIComponent(ref_)}`, {
    deps: [ref_],
  });
  const [confirm, setConfirm] = useState(false);
  const [removing, setRemoving] = useState(null); // the item being taken out
  const [failReason, setFailReason] = useState("");
  const [replacing, setReplacing] = useState(null); // the item a replacement is being picked for
  const [returning, setReturning] = useState(false);
  const [notesNow, setNotesNow] = useState(null);
  const [addrPick, setAddrPick] = useState(null); // an address id while changing where it goes
  /* Who takes it, and what happens when it does not get there
     (order_delivery.py). */
  const post = async (what, body, done) => {
    try {
      const r = await api(`/admin/orders/${encodeURIComponent(ref_)}/${what}`, { method: "POST", body });
      if (done) flash?.(done(r));
      await reload();
      onChanged?.();
    } catch (e) {
      flash?.(e?.message || "That did not go through.");
    }
  };
  const failed = (then) => post("failed", { reason: failReason || o.failReasons?.[0], then }, (r) =>
    then === "retry" ? `#${ref_} goes out again with a new door code`
      : r?.refund ? `#${ref_} returned · ${money(r.refund, o.currency)} to the 369 Wallet` : `#${ref_} returned to the store`);
  /* Out of stock: take one item out. Paid orders get its price back in the
     369 Wallet at once; cash orders owe less at the door. */
  const removeLine = async (line) => {
    try {
      const r = await api(`/admin/orders/${encodeURIComponent(ref_)}/remove`, {
        method: "POST", body: { line_id: line.lineId, reason: "Out of stock" } });
      flash?.(r?.refund ? `${line.name} taken out · ${money(r.refund, o.currency)} to the 369 Wallet` : `${line.name} taken out`);
      await reload();
      onChanged?.();
    } catch (e) {
      flash?.(e?.message || "Could not take that item out.");
    }
  };
  const [reason, setReason] = useState("");
  const o = data?.order;

  useEffect(() => { setReason(reasons?.[0] || ""); }, [reasons]);

  const act = async (fn) => {
    const ok = await fn();
    if (ok) await reload();
    return ok;
  };

  return (
    <>
      <Drawer wide onClose={onClose}
        title={`Order #${ref_}`}
        sub={o ? `${dateTime(o.at)} · ${modeLabel(o.mode)}` : "Loading…"}
        foot={(close) => (
          <>
            {o && (
              <a className="ad-btn" href={`/api/mart/admin/orders/print?kind=slips&refs=${encodeURIComponent(ref_)}`}
                target="_blank" rel="noreferrer"><Icon n="printer" size={16} />Packing slip</a>
            )}
            {o?.hasInvoice && (
              <a className="ad-btn" href={`/api/mart/admin/orders/${encodeURIComponent(ref_)}/invoice`}
                target="_blank" rel="noreferrer"><Icon n="printer" size={16} />Invoice</a>
            )}
            {/* Hidden rather than disabled once it is packed: the model refuses
                it, so offering the button at all is a trap. */}
            {o?.canCancel && (
              <button className="ad-btn ad-danger-ghost" disabled={busy}
                onClick={() => setConfirm(true)}>Cancel order</button>
            )}
            {o?.next && (
              <button className="ad-btn ad-primary" disabled={busy}
                onClick={() => act(() => onAdvance(o))}>
                {o.next.label}<Icon n="right" size={15} />
              </button>
            )}
            {o?.next ? <button className="ad-btn" onClick={close}>Close</button>
              : <button className="ad-btn ad-primary" onClick={close}>Close</button>}
          </>
        )}>

        {error && <Empty icon="info" title="We could not reach the shop" text={error.message}
          action="Try again" onAction={reload} />}
        {loading && !o && !error && <Empty icon="box" title="Loading…" text="Fetching the order." />}

        {o && (
          <>
            {/* 1. Where it is, and what to do now - the answer first. */}
            <section className="ad-dsec ad-ord-now">
              <ol className="ad-ord-steps">
                {(() => {
                  const stamped = Object.fromEntries((o.timeline || []).map((t) => [t.state, t]));
                  const reached = o.flow.filter((k) => stamped[k]).length;
                  return o.flow.map((k, i) => (
                    <li key={k} className={(stamped[k] ? "ad-done" : "") + (i === reached - 1 && !["delivered", "cancelled"].includes(o.state) ? " ad-on" : "")}>
                      <i /><b>{STATUS[k].label}</b><small>{stamped[k] ? clock(stamped[k].at) : ""}</small>
                    </li>
                  ));
                })()}
              </ol>
              <p className={"ad-ord-status" + (o.late ? " ad-ord-late" : "")}><Icon n={o.late ? "info" : "clock"} size={14} />{statusLine(o)}</p>
              {o.next && (
                <div className="ad-ord-next">
                  <span>Next step</span>
                  <button className="ad-btn ad-primary" disabled={busy} onClick={() => act(() => onAdvance(o))}>
                    {o.next.label}<Icon n="right" size={15} />
                  </button>
                </div>
              )}
            </section>

            {/* 2. Who, where, when. */}
            <section className="ad-dsec">
              <h4><Icon n="user" size={14} />Who</h4>
              <div className="ad-ord-who">
                <button type="button" className="ad-ord-name" disabled={!o.customer.userId}
                  onClick={() => onOpenCustomer?.(o.customer.userId)}>
                  {o.customer.name}{o.customer.userId && <Icon n="right" size={14} />}
                </button>
                <small>{(o.customer.orderCount || 0) <= 1 ? "first order" : `${o.customer.orderCount} orders so far`}</small>
                {(o.customer.tags || []).map((t) => <span key={t.id} className={"ad-pill ad-t-" + TAG_TONES[(t.color || 0) % TAG_TONES.length]}>{t.name}</span>)}
              </div>
              {riskLine(o.customer.risk) && <p className="ad-risk-line"><Icon n="info" size={14} />{riskLine(o.customer.risk)}</p>}
              <div className="ad-cust-reach">
                {o.customer.phone && <a className="ad-btn ad-sm" href={`tel:${o.customer.phone.replace(/[^\d+]/g, "")}`}><Icon n="phone" size={14} />Call</a>}
                {o.customer.waPhone && <a className="ad-btn ad-sm" href={`https://wa.me/${o.customer.waPhone}`} target="_blank" rel="noopener noreferrer"><Icon n="chat" size={14} />WhatsApp</a>}
              </div>

              <h5 className="ad-ord-h5">Deliver to</h5>
              {addrPick === null ? (
                <div className="ad-ord-addr">
                  <span>
                    {o.address ? (
                      <>
                        <b>{[o.address.label, o.address.name, o.address.phone].filter(Boolean).join(" · ")}</b>
                        <small>{addrLines(o.address).join(", ")}</small>
                      </>
                    ) : <small>No address on the order.</small>}
                  </span>
                  {o.addressChangeable && (o.addresses || []).length > 1 && (
                    <button className="ad-btn ad-sm" onClick={() => setAddrPick(o.address?.id ?? null)}>Change</button>
                  )}
                </div>
              ) : (
                <div className="ad-ord-addrpick">
                  {(o.addresses || []).map((a) => (
                    <label key={a.id} className={addrPick === a.id ? "ad-on" : ""}>
                      <input type="radio" name="ad-addr" checked={addrPick === a.id} onChange={() => setAddrPick(a.id)} />
                      <span><b>{a.label}{o.address && a.id === o.address.id ? " (now)" : ""}</b><small>{addrLines(a).join(", ")}</small></span>
                    </label>
                  ))}
                  <span className="ad-cust-note-edit-act">
                    <button className="ad-btn ad-sm" onClick={() => setAddrPick(null)}>Cancel</button>
                    <button className="ad-btn ad-sm ad-primary" disabled={busy || !o.address || addrPick === o.address.id}
                      onClick={async () => { const id = addrPick; setAddrPick(null); await post("address", { address_id: id }, () => "Delivery address changed"); }}>
                      Deliver here</button>
                  </span>
                </div>
              )}
              <p className="ad-ord-line"><b>When</b>{[o.slot, o.dueAt ? `promised by ${dateTime(o.dueAt)}` : ""].filter(Boolean).join(" · ") || "—"}</p>
              {o.instructions && <p className="ad-ord-line"><b>Customer's note</b>{o.instructions}</p>}
            </section>

            {/* 3. What's in it, and the money. */}
            <section className="ad-dsec">
              <h4><Icon n="bag" size={14} />Items <em>{o.items.length}</em></h4>
              <ul className="ad-items">
                {o.items.map((l, i) => (
                  <li key={i}>
                    <span className="ad-qty-chip">{l.qty}×</span>
                    <span><b>{l.name}</b></span>
                    <b>{money(l.price * l.qty, o.currency)}</b>
                    {(() => {
                      const offer = (o.substitutes || []).find((x) => x.lineId === l.lineId && x.state === "offered");
                      if (offer) {
                        return (
                          <span className="ad-offer">
                            <Icon n="clock" size={12} />{offer.offered} offered · waiting · {leftOf(offer.deadline)}
                            <button className="ad-btn ad-sm" disabled={busy}
                              onClick={() => post(`substitute/${offer.id}/withdraw`, {}, () => "Offer withdrawn")}>Withdraw</button>
                          </span>
                        );
                      }
                      return (
                        <>
                          {o.canReplace && (
                            <button className="ad-btn ad-sm ad-replace" disabled={busy}
                              title="Out of stock: offer the customer something else" onClick={() => setReplacing(l)}>Replace</button>
                          )}
                          {o.canRemove && (
                            <button className="ad-btn ad-sm ad-remove" disabled={busy}
                              title="Out of stock: take it out and refund it" onClick={() => setRemoving(l)}>Remove</button>
                          )}
                        </>
                      );
                    })()}
                  </li>
                ))}
              </ul>
              {!!(o.removed || []).length && (
                <p className="ad-ord-gone"><b>Taken out or replaced: </b>
                  {o.removed.map((g) => `${g.qty}× ${g.name}${g.reason ? ` (${g.reason})` : ""}${g.refund ? ` · ${money(g.refund, o.currency)} to wallet` : ""}`).join("; ")}
                </p>
              )}
              <dl className="ad-bill">
                <div><dt>Items</dt><dd>{money(o.bill.items, o.currency)}</dd></div>
                <div><dt>Delivery</dt><dd>{o.bill.fees ? money(o.bill.fees, o.currency) : "Free"}</dd></div>
                {!!o.bill.couponOff && (
                  <div><dt>Coupon {o.coupon ? `· ${o.coupon}` : ""}</dt>
                    <dd>−{money(o.bill.couponOff, o.currency)}</dd></div>
                )}
                {!!o.walletUsed && (
                  <div><dt>From wallet</dt><dd>−{money(o.walletUsed, o.currency)}</dd></div>
                )}
                <div className="ad-bill-total"><dt>Total</dt><dd>{money(o.bill.total, o.currency)}</dd></div>
              </dl>
              <p className="ad-ord-pay"><Icon n="cash" size={14} />{payLine(o)}</p>
            </section>

            {/* 4. Getting it there. */}
            <section className="ad-dsec">
              <h4><Icon n="truck" size={14} />Delivery</h4>
              <div className="ad-ord-rider">
                <span>Rider</span>
                {o.riders?.length ? (
                  <Select value={o.riderId ? String(o.riderId) : ""} label="Rider"
                    options={[["", "No rider yet"], ...o.riders.map((r) => [String(r.id), r.name])]}
                    onChange={(v) => post("rider", { user_id: Number(v) || false }, () => (v ? "Rider set" : "Rider removed"))} />
                ) : (
                  <small>Nobody has the Rider role yet — give it under Staff &amp; roles.</small>
                )}
              </div>
              <p className="ad-ord-line"><b>Door code</b>
                {!o.otp.issuedAt
                  ? "No code has been issued for this order yet."
                  : o.otp.usedAt
                    ? `Used at ${clock(o.otp.usedAt)} on ${dateShort(o.otp.usedAt)}.`
                    : `Issued ${clock(o.otp.issuedAt)}, not used yet. The customer has it in their app.`}
              </p>
              {!!o.attempts && (
                <p className="ad-failed"><Icon n="info" size={14} />Attempt {o.attempts} failed: {o.failedReason}</p>
              )}
              {o.canFail && (
                <div className="ad-fail">
                  <b>Couldn't deliver?</b>
                  <Select value={failReason || o.failReasons?.[0] || ""} label="What went wrong"
                    options={(o.failReasons || []).map((r) => [r, r])} onChange={setFailReason} />
                  <button className="ad-btn ad-sm" disabled={busy} onClick={() => failed("retry")}>Try again</button>
                  <button className="ad-btn ad-sm ad-danger-ghost" disabled={busy} onClick={() => setReturning(true)}>Return to store</button>
                </div>
              )}
            </section>

            {/* 5. The team's notes on it. */}
            <OrderNotes ref_={ref_} notes={notesNow || o.notes || []} onSaved={setNotesNow} />

            {/* 6. Anything the customer raised about it. */}
            {(!!(o.tickets || []).length || !!o.returns.length) && (
              <section className="ad-dsec">
                <h4><Icon n="chat" size={14} />Support &amp; returns</h4>
                <ul className="ad-prof-list">
                  {(o.tickets || []).map((t) => (
                    <li key={"t" + t.id}>
                      <button type="button" onClick={() => onOpenTicket?.(t.ref)}>
                        <span><b>{t.ref} · {t.subject}</b><small>{t.stateLabel || t.state}</small></span>
                        <Icon n="right" size={14} />
                      </button>
                    </li>
                  ))}
                  {o.returns.map((r) => (
                    <li key={"r" + r.id}>
                      <div><span><b>{r.kind === "replace" ? "Replacement" : "Refund"}: {r.reason}</b><small>{r.state}</small></span>
                        {!!r.amount && <b>{money(r.amount, o.currency)}</b>}</div>
                    </li>
                  ))}
                </ul>
              </section>
            )}

            {/* 7. Who did what, when - folded away. */}
            <details className="ad-dsec ad-ord-history">
              <summary>History{(o.activity || []).length ? ` · ${o.activity.length} updates` : ""}</summary>
              {!!(o.activity || []).length && (
                <ul className="ad-ord-activity">
                  {o.activity.map((n) => <li key={n.id}><p>{n.text}</p><small>{n.author} · {n.at ? since(n.at) : ""}</small></li>)}
                </ul>
              )}
              <Timeline o={o} />
            </details>
          </>
        )}
      </Drawer>

      {replacing && o && (
        <ReplacePicker order={o} line={replacing} onCancel={() => setReplacing(null)}
          onSend={async (productId) => {
            setReplacing(null);
            await post("substitute", { line_id: replacing.lineId, product_ids: productId },
              () => `Replacement sent - #${o.ref} waits for the customer`);
          }} />
      )}

      {returning && o && (
        <Confirm danger title={`Return #${o.ref} to the store?`} confirmLabel="Return to store"
          text={o.method === "cod"
            ? `The order is closed as "${failReason || o.failReasons?.[0]}". It was cash on delivery, so there is nothing to refund.`
            : `The order is closed as "${failReason || o.failReasons?.[0]}" and ${money(o.paid || o.total, o.currency)} goes to the customer's 369 Wallet straight away.`}
          onCancel={() => setReturning(false)}
          onConfirm={async () => { setReturning(false); await failed("return"); }} />
      )}

      {removing && o && (
        <Confirm danger title={`Take ${removing.qty} × ${removing.name} out of #${o.ref}?`} confirmLabel="Take it out"
          text={o.method === "cod"
            ? `It is marked out of stock and the cash to collect drops by ${money(removing.price * removing.qty, o.currency)}.`
            : `It is marked out of stock and ${money(removing.price * removing.qty, o.currency)} goes to the customer's 369 Wallet straight away.`}
          onCancel={() => setRemoving(null)}
          onConfirm={async () => { const l = removing; setRemoving(null); await removeLine(l); }} />
      )}

      {confirm && o && (
        <Confirm danger title={`Cancel order #${o.ref}?`} confirmLabel="Cancel order"
          text={
            <>
              {o.method === "cod" ? "It was cash on delivery, so nothing is refunded."
                : `${money(o.paid || o.bill.total, o.currency)} goes to the customer's 369 Wallet straight away.`} The customer sees
              the reason on their own tracking screen, so pick one that reads
              well there.
              <br />
              <select className="ad-reason" value={reason} onChange={(e) => setReason(e.target.value)}>
                {(reasons || []).map((r) => <option key={r}>{r}</option>)}
              </select>
            </>
          }
          onCancel={() => setConfirm(false)}
          onConfirm={async () => { setConfirm(false); await act(() => onCancel(o, reason)); }} />
      )}
    </>
  );
}

/* "8 min left" on a replacement the customer has not answered. */
const leftOf = (ms) => {
  const m = Math.max(0, Math.round((ms - Date.now()) / 60000));
  return m < 60 ? `${m} min left` : `${Math.round(m / 60)} h left`;
};

/* Pick a replacement for an item that ran out and send it to the customer,
   who accepts or refuses it on their order page. */
function ReplacePicker({ order, line, onCancel, onSend }) {
  const [q, setQ] = useState("");
  const [picked, setPicked] = useState([]); // up to three; the customer picks one
  const toggle = (id) => setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : p.length < 3 ? [...p, id] : p));
  const [products, setProducts] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    const id = setTimeout(async () => {
      try {
        const p = new URLSearchParams({ line_id: String(line.lineId) });
        if (q.trim()) p.set("q", q.trim());
        const r = await api(`/admin/orders/${encodeURIComponent(order.ref)}/substitutes?${p}`, { fresh: true });
        setProducts(r?.products || []);
        setError("");
      } catch (e) {
        setError(e?.message || "Could not load products.");
      }
    }, 300);
    return () => clearTimeout(id);
  }, [q, order.ref, line.lineId]);
  if (typeof document === "undefined") return null;
  return createPortal(
    <div className="ad-modal-wrap" onClick={onCancel}>
      <div className="ad-modal ad-replace-modal" role="dialog" aria-modal="true" aria-label="Offer a replacement" onClick={(e) => e.stopPropagation()}>
        <h3>Offer a replacement</h3>
        <p><b>{line.name}</b> ({line.qty} × {money(line.price, order.currency)}) is out of stock. Tick up to three — the customer picks one on their order page and pays no more than they did.</p>
        <label className="ad-field">
          <span className="ad-field-in"><input autoFocus value={q} placeholder="Search products" onChange={(e) => setQ(e.target.value)} aria-label="Search products" /></span>
        </label>
        {error && <p className="ad-failed">{error}</p>}
        <ul className="ad-replace-list">
          {products === null && <li className="ad-dim">Looking…</li>}
          {products && !products.length && <li className="ad-dim">Nothing in stock matches.</li>}
          {(products || []).map((p) => (
            <li key={p.id}>
              <button type="button" className={picked.includes(p.id) ? "ad-on" : ""} onClick={() => toggle(p.id)} aria-pressed={picked.includes(p.id)}>
                {p.image ? <img src={p.image} alt="" /> : <span className="ad-replace-img" />}
                <span><b>{p.name}</b>
                  <small>{money(p.price, order.currency)}
                    {p.shopPays ? ` · shop pays +${money(p.shopPays, order.currency)}` : ""}
                    {p.toWallet ? ` · ${money(p.toWallet, order.currency)} back to the customer` : ""}</small></span>
              </button>
            </li>
          ))}
        </ul>
        <div>
          <button type="button" className="ad-btn" onClick={onCancel}>Cancel</button>
          <button type="button" className="ad-btn ad-primary" disabled={!picked.length} onClick={() => onSend(picked)}>Send {picked.length || ""} to customer</button>
        </div>
      </div>
    </div>,
    document.body
  );
}

/* The doorstep, as a dialog.

   Its own component so the code lives nowhere but here: it is typed, sent and
   forgotten, never held in the section's state where a re-render could leave
   it lying about. The box keeps the focus and the dialog stays open when the
   shop refuses, because a wrong digit is the likeliest outcome and closing
   would make the operator ask for the whole code again. */
function DeliverPrompt({ order, busy, onClose, onDeliver }) {
  const [code, setCode] = useState("");
  const [error, setError] = useState("");

  const send = async () => {
    setError("");
    const ok = await onDeliver(order, code.trim());
    if (ok !== true) {
      setError(ok?.error || "That did not go through.");
      setCode("");
      return;
    }
    onClose();
  };

  return (
    <Confirm title={`Delivered #${order.ref}?`} confirmLabel="Mark delivered"
      text={
        <>
          The customer has the code on their own order screen. Ask for it at the
          door — it is the only thing that closes a delivery, and it works once.
          <br />
          <input className="ad-otp-in" value={code} inputMode="numeric"
            autoFocus maxLength={6} placeholder="000000"
            aria-label="Delivery code"
            onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
            onKeyDown={(e) => { if (e.key === "Enter" && code.trim()) send(); }} />
          {error && <span className="ad-otp-bad" role="alert">{error}</span>}
        </>
      }
      onCancel={onClose}
      onConfirm={() => { if (!busy && code.trim()) send(); }} />
  );
}

/* A new order's chime: two short notes made here, so there is no sound file.
   Browsers only play sound after a click on the page - switching "Sound on"
   is that click. */
const SOUND_KEY = "mart369.orders.sound";
let audio = null;
function chime() {
  try {
    audio = audio || new (window.AudioContext || window.webkitAudioContext)();
    if (audio.state === "suspended") audio.resume();
    const start = audio.currentTime;
    [880, 1318.5].forEach((freq, i) => {
      const osc = audio.createOscillator();
      const gain = audio.createGain();
      osc.type = "sine";
      osc.frequency.value = freq;
      const at = start + i * 0.16;
      gain.gain.setValueAtTime(0.0001, at);
      gain.gain.exponentialRampToValueAtTime(0.25, at + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.0001, at + 0.35);
      osc.connect(gain).connect(audio.destination);
      osc.start(at);
      osc.stop(at + 0.4);
    });
  } catch { /* no sound here - the toast still says it */ }
}
const soundWanted = () => { try { return localStorage.getItem(SOUND_KEY) !== "off"; } catch { return true; } };

export default function OrdersSection({ openId, setOpenId, query = "", flash, onOpenCustomer, onOpenTicket }) {
  const [tab, setTab] = useState("needs");
  const [mode, setMode] = useState("");
  const [when, setWhen] = useState("all");
  const [pay, setPay] = useState("");
  const [sort, setSort] = useState("due");
  const [term, setTerm] = useState(query);
  const [q, setQ] = useState(query);
  const [sel, setSel] = useState([]);
  const [deliver, setDeliver] = useState(null); // the order waiting on a code
  const [limit, setLimit] = useState(PAGE);

  /* The topbar can hand a term over from another section. */
  useEffect(() => { if (query) { setTerm(query); setTab("all"); } }, [query]);

  /* Searched on the server, so the box is debounced rather than filtering a
     list the browser happens to be holding. Same 300ms as the product
     builder's product search. */
  useEffect(() => {
    const id = setTimeout(() => { setQ(term.trim()); setLimit(PAGE); }, 300);
    return () => clearTimeout(id);
  }, [term]);

  const path = useMemo(() => {
    const p = new URLSearchParams({ tab, sort, limit: String(limit) });
    if (mode) p.set("mode", mode);
    if (when !== "all") p.set("when", when);
    if (pay) p.set("pay", pay);
    if (q) p.set("q", q);
    return "/admin/orders?" + p.toString();
  }, [tab, mode, when, pay, sort, q, limit]);

  const { data, loading, error, reload } = useResource(path, { pollMs: 30000, keepLast: true });
  const counts = useResource("/admin/orders/counts", { pollMs: 30000 });

  /* A toast, and a chime, for every order placed since the screen last looked.
     The first look only remembers what is there. */
  const [sound, setSound] = useState(true);
  useEffect(() => { setSound(soundWanted()); }, []);
  const seen = useRef(null);
  useEffect(() => {
    const latest = counts.data?.latest;
    if (!latest) return;
    if (!seen.current) { seen.current = new Set(latest.map((o) => o.ref)); return; }
    const fresh = latest.filter((o) => !seen.current.has(o.ref));
    if (!fresh.length) return;
    fresh.forEach((o) => seen.current.add(o.ref));
    flash?.(fresh.length === 1
      ? `New order #${fresh[0].ref} · ${money(fresh[0].total, fresh[0].currency)}`
      : `${fresh.length} new orders · #${fresh.map((o) => o.ref).join(", #")}`);
    if (sound) chime();
  }, [counts.data, sound, flash]);
  const toggleSound = () => {
    const next = !sound;
    setSound(next);
    try { localStorage.setItem(SOUND_KEY, next ? "on" : "off"); } catch { /* this visit only */ }
    if (next) chime();
  };
  const act = useAction();

  const rows = data?.orders || [];
  const total = data?.total || 0;
  const reasons = data?.reasons || [];

  const refresh = async () => {
    api.invalidate("/admin/orders");
    await Promise.all([reload(), counts.reload()]);
  };

  /* Read-after-write. `next`, `late` and the tile numbers are all the
     server's, so there is nothing safe to patch locally. */
  const run = (fn, ok) => {
    let failure = null;
    return act.run(async () => {
      try { await fn(); } catch (e) { failure = e; throw e; }
      await refresh();
      if (ok) flash?.(ok);
      return true;
    }).then((r) => {
      if (r === null) flash?.(failure?.message || "That did not work.", "bad");
      return r;
    });
  };

  /* Delivered is not a step this board takes. Every other state is the shop
     moving its own work along; that one is the customer saying they have their
     things, and the code from their screen is the only evidence of it. The
     server refuses an advance into delivered, so asking here is not politeness
     - it is the only route through. */
  const needsCode = (o) => o.next?.state === "delivered";

  const advance = (o) =>
    needsCode(o)
      ? setDeliver(o)
      : run(() => api(`/admin/orders/${encodeURIComponent(o.ref)}/advance`, { method: "POST" }),
        `#${o.ref} → ${(STATUS[o.next?.state]?.label || "moved on").toLowerCase()}`);

  const deliverOrder = async (o, code) => {
    try {
      await api(`/admin/orders/${encodeURIComponent(o.ref)}/deliver`, { method: "POST", body: { code } });
    } catch (e) {
      return { error: e.field === "code" ? "That code is not right. Ask the customer to read it again." : (e.message || "That did not go through.") };
    }
    await refresh();
    flash?.(`#${o.ref} delivered`);
    return true;
  };

  const cancelOrder = (o, reason) =>
    run(() => api(`/admin/orders/${encodeURIComponent(o.ref)}/cancel`, {
      method: "POST", body: { reason },
    }), `#${o.ref} cancelled`);

  /* Sequenced, and one reload at the end. Firing N unawaited writes and
     reloading after the first is how a bulk action reports success for orders
     the shop refused. */
  const bulkAdvance = () =>
    act.run(async () => {
      /* Orders at the door are left out rather than attempted: each one needs
         its own code, so a bulk button could only ever fail on them, and
         reporting "3 of 5 moved on" would read like a fault. */
      const chosen = rows.filter((o) => sel.includes(o.ref) && o.next);
      const atDoor = chosen.filter(needsCode);
      const picked = chosen.filter((o) => !needsCode(o));
      let done = 0;
      const failed = [];
      for (const o of picked) {
        try {
          await api(`/admin/orders/${encodeURIComponent(o.ref)}/advance`, { method: "POST" });
          done += 1;
        } catch (e) {
          failed.push(o.ref);
        }
      }
      await refresh();
      setSel([]);
      const note = atDoor.length
        ? ` ${atDoor.length} at the door need${atDoor.length === 1 ? "s" : ""} a delivery code.`
        : "";
      if (!failed.length) flash?.(`${done} order${done === 1 ? "" : "s"} moved on.${note}`);
      else flash?.(`${done} of ${picked.length} moved on. ${failed.join(", ")} did not.${note}`, "bad");
      return true;
    });

  /* What is on screen, not what is in the shop. Saying so on the button keeps
     an operator from mailing a "full export" that is one page long. */
  const exportCsv = () => {
    const head = ["Order", "Placed", "Mode", "Customer", "Phone", "Area", "Items", "Total", "Payment", "Status", "Late"];
    const body = rows.map((o) => [o.ref, dateTime(o.at), modeLabel(o.mode), o.customer.name,
      o.customer.phone, o.customer.area, o.itemCount, o.total, o.payNote || o.method,
      STATUS[o.state]?.label || o.state, o.late ? "yes" : ""]);
    const csv = [head, ...body].map((r) => r.map((c) => `"${String(c ?? "").replace(/"/g, '""')}"`).join(",")).join("\n");
    try {
      const url = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
      const a = document.createElement("a");
      a.href = url;
      a.download = `369mart-orders-${dateShort(Date.now()).replace(/ /g, "-")}.csv`;
      a.click();
      URL.revokeObjectURL(url);
      flash(`${rows.length} orders exported`);
    } catch (e) { flash("Export failed", "bad"); }
  };

  const pick = (next) => { setTab(next); setLimit(PAGE); setSel([]); };
  const shownSel = rows.filter((o) => sel.includes(o.ref));
  const allShown = rows.length > 0 && rows.every((o) => sel.includes(o.ref));

  return (
    <div className="ad-stack">
      <Tiles counts={counts.data?.counts} cashDue={counts.data?.cashDue} tab={tab} onPick={pick} />

      <section className="ad-card">
        <div className="ad-toolbar">
          <Tabs value={tab} onChange={pick}
            tabs={TABS.map(([k, label, badge]) => [k, label, badge ? counts.data?.counts?.[badge] : null])} />
          <div className="ad-toolbar-right">
            <Search value={term} onChange={setTerm} placeholder="Order, name or phone" />
            <Select value={mode} onChange={(v) => { setMode(v); setLimit(PAGE); }} label="Type"
              options={[["", "All types"], ["quick", "Quick"], ["all", "Express"]]} />
            <Select value={when} onChange={(v) => { setWhen(v); setLimit(PAGE); }} label="Period"
              options={[["all", "All time"], ["today", "Today"], ["7d", "Last 7 days"]]} />
            <Select value={pay} onChange={(v) => { setPay(v); setLimit(PAGE); }} label="Payment"
              options={[["", "Any payment"], ["cod", "Cash on delivery"], ["prepaid", "Prepaid"]]} />
            <Select value={sort} onChange={(v) => { setSort(v); setLimit(PAGE); }} label="Sort"
              options={[["due", "Most urgent first"], ["old", "Longest wait first"], ["new", "Newest first"], ["value", "Highest value"]]} />
            <button className="ad-btn" onClick={toggleSound} aria-pressed={sound}
              title={sound ? "A chime plays for each new order" : "New orders arrive silently"}>
              <Icon n={sound ? "bell" : "bellOff"} size={16} />{sound ? "Sound on" : "Sound off"}
            </button>
            <button className="ad-btn" onClick={exportCsv} disabled={!rows.length}>
              <Icon n="download" size={16} />Export these
            </button>
          </div>
        </div>

        <div className={"ad-bulk" + (sel.length ? " ad-show" : "")}>
          <span><b>{sel.length}</b> selected</span>
          <button className="ad-btn ad-sm" onClick={bulkAdvance}
            disabled={act.busy || !shownSel.some((o) => o.next && !needsCode(o))}>Move all on</button>
          {/* PDFs for the ticked orders: one slip per order to go in the bag,
              and one picklist for walking the store once. */}
          <a className="ad-btn ad-sm" target="_blank" rel="noreferrer"
            href={`/api/mart/admin/orders/print?kind=slips&refs=${encodeURIComponent(sel.join(","))}`}>
            <Icon n="printer" size={14} />Packing slips</a>
          <a className="ad-btn ad-sm" target="_blank" rel="noreferrer"
            href={`/api/mart/admin/orders/print?kind=picklist&refs=${encodeURIComponent(sel.join(","))}`}>
            <Icon n="printer" size={14} />Picklist</a>
          <button className="ad-link" onClick={() => setSel([])}>Clear</button>
        </div>

        {/* Only take the list away when there is nothing left to show. A
            failed poll on a screen that already has orders on it keeps the
            orders and says so in a line: a packer mid-shift needs the list
            more than they need the error, and clearing it would also replay
            every row's entrance when the next tick succeeds. */}
        {error && !rows.length && (
          <Empty icon="info" title="We could not reach the shop" text={error.message}
            action="Try again" onAction={reload} />
        )}
        {error && !!rows.length && (
          <p className="ad-hint" role="status">
            <Icon n="info" size={15} />
            <span>Could not reach the shop just now, so this is the last read.
              <button className="ad-link" onClick={reload}>Try again</button></span>
          </p>
        )}
        {loading && !rows.length && !error && (
          <Empty icon="box" title="Loading…" text="Fetching orders." />
        )}

        {!!rows.length && (
          <ul className="ad-orders">
            <li className="ad-orders-head">
              <input type="checkbox" checked={allShown} aria-label="Select all"
                onChange={(e) => setSel(e.target.checked ? rows.map((o) => o.ref) : [])} />
              <span>{total} order{total === 1 ? "" : "s"}{q ? ` matching “${q}”` : ""}</span>
            </li>
            {groupRows(tab, rows).map((g) => (
              <li key={"g-" + g.key} className="ad-order-group">
                {g.label && <h3>{g.label}<em>{g.rows.length}</em></h3>}
                <ul>
            {g.rows.map((o, i) => (
              <li key={o.ref} style={{ "--i": i % PAGE }}
                className={"ad-order ad-order2" + (sel.includes(o.ref) ? " ad-selected" : "") + (o.late ? " ad-order-late" : "")}
                onClick={(e) => { if (!e.target.closest("button,input,select,a")) setOpenId(o.ref); }}>
                <input type="checkbox" checked={sel.includes(o.ref)} aria-label={`Select ${o.ref}`}
                  onChange={(e) => setSel((s) => (e.target.checked ? [...s, o.ref] : s.filter((x) => x !== o.ref)))} />

                {/* Who first: the name is what a person reads out. */}
                <div className="ad-order2-main">
                  <div className="ad-order2-top">
                    <b>{o.customer.name}</b>
                    {o.customer.area && <small>· {o.customer.area}</small>}
                    {(o.customer.tags || []).map((t) => <span key={t.id} className={"ad-pill ad-t-" + ROW_TONES[(t.color || 0) % ROW_TONES.length]}>{t.name}</span>)}
                    {o.customer.codOff && <span className="ad-pill ad-t-red">COD off</span>}
                  </div>
                  <small className="ad-order2-sub">
                    #{o.ref} · <Icon n={o.mode === "quick" ? "bolt" : "truck"} size={12} /> {modeLabel(o.mode)} · {o.itemCount} item{o.itemCount === 1 ? "" : "s"} · {since(o.at)}
                  </small>
                  <div className="ad-order2-facts">
                    {(g.key === "all" || g.key === "other") && <Pill s={o.state} map={STATUS} />}
                    {o.late
                      ? <span className="ad-late"><Icon n="info" size={13} />{overdueBy(o.dueAt)}</span>
                      : o.dueAt && LIVE.includes(o.state)
                        ? <span className="ad-order-promise ad-due"><Icon n="clock" size={13} />{dueIn(o.dueAt)}</span>
                        : null}
                    <span className={"ad-order2-pay" + (o.method === "cod" && !["delivered", "cancelled"].includes(o.state) ? " ad-order2-cash" : "")}>
                      <Icon n={o.method === "cod" ? "cash" : "check"} size={13} />{payText(o)}
                    </span>
                    {o.rider && <span className="ad-order-pay">🛵 {o.rider}</span>}
                    {o.substituteUntil && <span className="ad-waiting"><Icon n="clock" size={12} />Replacement waiting · {leftOf(o.substituteUntil)}</span>}
                    {!!o.attempts && o.state === "out" && <span className="ad-late"><Icon n="info" size={13} />{o.attempts} failed {o.attempts === 1 ? "try" : "tries"} — {o.failedReason}</span>}
                  </div>
                </div>
                <div className="ad-order2-side">
                  <b>{money(o.total, o.currency)}</b>
                  {o.next && (
                    <button className="ad-btn ad-sm ad-primary" disabled={act.busy}
                      onClick={() => advance(o)}>{o.next.label}<Icon n="right" size={13} /></button>
                  )}
                </div>
              </li>
            ))}
                </ul>
              </li>
            ))}
          </ul>
        )}

        {!error && !loading && !rows.length && (
          <Empty icon="box"
            title={tab === "needs" ? "Nothing waiting" : "No orders here"}
            text={tab === "needs"
              ? "Every order has been dealt with. New ones appear here on their own."
              : "Try another tab, period or search."} />
        )}

        {rows.length < total && (
          <div className="ad-more">
            <button className="ad-btn" onClick={() => setLimit((l) => l + PAGE)} disabled={loading}>
              Show more ({total - rows.length} left)
            </button>
          </div>
        )}
      </section>

      {openId && (
        <OrderDrawer ref_={openId} reasons={reasons} busy={act.busy} flash={flash}
          onClose={() => setOpenId(null)}
          onOpenCustomer={onOpenCustomer}
          onOpenTicket={onOpenTicket}
          onAdvance={advance}
          onChanged={reload}
          onCancel={cancelOrder} />
      )}

      {deliver && (
        <DeliverPrompt order={deliver} busy={act.busy}
          onClose={() => setDeliver(null)}
          onDeliver={deliverOrder} />
      )}
    </div>
  );
}
