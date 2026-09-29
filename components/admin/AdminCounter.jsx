"use client";
/* ==========================================================================
   369 Mart admin — Orders › Counter

   The shop counter: every paid order the shop still has to handle, website
   and WhatsApp alike, with New / Quick / Express tabs. It is the Store's own
   queue (sales_automation_store) through mart369_store_board's
   /369mart/admin/counter, so accepting here accepts at the Odoo counter too.

   Drawn exactly like All orders (AdminOrders.jsx) - the same rows, pills and
   buttons - because it is the same orders; the server hands each row over in
   All orders' own shape. A click opens the order in All orders' drawer.

   The alarm is not this screen's: it lives in the console shell
   (`useCounterAlarm`, used by AdminApp.jsx), so it keeps ringing while an
   order waits whichever section is open - Counter, All orders or anything
   else. Like the Odoo counter it has no off switch: it arms on the first
   click anywhere and stops only when the orders are accepted.
   ========================================================================== */
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { money } from "@/lib/money";
import { useAction, useResource } from "@/lib/useFetch";
import { Empty, Icon, Tabs } from "./AdminUI";
import { since } from "./format";
import { modeLabel, payText, ROW_TONES } from "./AdminOrders";
import { Alarm } from "./counterAlarm";

export const COUNTER_PATH = "/admin/counter";

const waitingOf = (rows) => (rows || []).filter((r) => r.counter === "awaiting_shop" && !r.supplyWaiting).length;

/* The console-wide alarm. Called once, in the shell.

   Rings while any order waits for Accept, at the counter's own cadence from
   Delivery Settings (`ring` seconds of the ring, then `repeat` seconds quiet),
   on every section. A browser only plays sound after a click, so it arms on
   the first click or key press anywhere - and from then on there is nothing
   to switch off: it stops when the orders are accepted. */
export function useCounterAlarm() {
  const [unavailable, setUnavailable] = useState(false);
  const { data, error } = useResource(COUNTER_PATH, { pollMs: 10000, keepLast: true, enabled: !unavailable });
  useEffect(() => { if (error?.status === 404 || error?.status === 403) setUnavailable(true); }, [error]);

  /* The Odoo counter's own sound (counterAlarm.js), one instance for the
     console. */
  const alarm = useRef(null);
  if (!alarm.current) alarm.current = new Alarm();
  const [armed, setArmed] = useState(false);
  const arm = async () => {
    const ok = await alarm.current.arm();
    if (ok) setArmed(true);
    return ok;
  };
  useEffect(() => {
    const onGesture = async () => {
      if (await arm()) {
        document.removeEventListener("pointerdown", onGesture, true);
        document.removeEventListener("keydown", onGesture, true);
      }
    };
    document.addEventListener("pointerdown", onGesture, true);
    document.addEventListener("keydown", onGesture, true);
    return () => {
      document.removeEventListener("pointerdown", onGesture, true);
      document.removeEventListener("keydown", onGesture, true);
    };
  }, []); // eslint-disable-line

  /* Exactly the Odoo counter's rhythm: ring for `ring` seconds, then quiet
     for `repeat`, again and again while an order waits. */
  const ringing = waitingOf(data?.rows);
  const ringFor = Math.max(3, data?.ring || 30);
  const pause = Math.max(3, data?.repeat || 10);
  useEffect(() => {
    const a = alarm.current;
    if (!armed || !ringing) { a.stop(); return undefined; }
    a.ring(ringFor);
    const id = setInterval(() => a.ring(ringFor), (ringFor + pause) * 1000);
    return () => { clearInterval(id); a.stop(); };
  }, [armed, ringing > 0, ringFor, pause]); // eslint-disable-line -- restart only when it starts or stops

  return { enabled: !unavailable && !!data, armed, ringing, arm };
}

/* Same three rules as the Odoo Counter (mart369_store_board). */
const TABS = [
  { key: "new", label: "New", match: (r) => r.counter === "awaiting_shop" },
  { key: "quick", label: "Quick", match: (r) => r.kind === "quick" },
  { key: "express", label: "Express", match: (r) => r.kind === "express" },
];

const STAGE = {
  awaiting_shop: { label: "New order", tone: "red" },
  preparing: { label: "Being packed", tone: "amber" },
  ready: { label: "Rider called", tone: "blue" },
  offered: { label: "Rider called", tone: "blue" },
  accepted: { label: "Rider on the way", tone: "violet" },
};

export default function CounterSection({ flash, onOpenOrder, onUnavailable, alarm }) {
  const [tab, setTab] = useState("new");
  const { data, loading, error, reload } = useResource(COUNTER_PATH, { pollMs: 5000, keepLast: true });
  const act = useAction();

  /* No board module on this shop: the console falls back to All orders. */
  useEffect(() => {
    if (error?.status === 404 && !data) onUnavailable?.();
  }, [error, data, onUnavailable]);

  const rows = data?.rows || [];
  const shown = rows.filter((TABS.find((t) => t.key === tab) || TABS[0]).match);
  const ringing = waitingOf(rows);
  const armed = !!alarm?.armed;

  /* ------------------------------------------------------------ the buttons */
  const run = (row, action, ok) => act.run(async () => {
    await api(`${COUNTER_PATH}/${row.job}`, { method: "POST", body: { action } });
    api.invalidate("/admin/orders");
    await reload();
    flash?.(ok);
    return true;
  }).then((r) => { if (r === null) flash?.("That did not go through. Try again.", "bad"); });

  const ref = (row) => row.order?.ref || row.code;

  return (
    <div className="ad-stack">
      <section className="ad-card">
        <div className="ad-toolbar">
          <Tabs value={tab} onChange={setTab}
            tabs={TABS.map((t) => [t.key, t.label, rows.filter(t.match).length])} />
          <div className="ad-toolbar-right">
            {ringing > 0 && <span className="ad-pill ad-t-red ad-counter-ringing">{ringing} new</span>}
            {/* No off switch: once on it rings on every section until the
                orders are accepted (useCounterAlarm, in the shell). */}
            {armed
              ? <span className="ad-counter-on" title="Rings on every screen while an order waits. It stops when the orders are accepted.">
                  <Icon n="bell" size={16} />Alarm on</span>
              : <button className="ad-btn ad-primary" onClick={() => alarm?.arm()}>
                  <Icon n="bell" size={16} />Turn on the alarm</button>}
          </div>
        </div>

        {!armed && (
          <p className="ad-hint" role="status">
            <Icon n="info" size={15} />
            <span>No sound yet. The browser plays nothing until you click - click anywhere, and from then on
              the alarm rings on every screen whenever an order is waiting.</span>
          </p>
        )}

        {error && !rows.length && error.status !== 404 && (
          <Empty icon="info" title="We could not reach the counter" text={error.message}
            action="Try again" onAction={reload} />
        )}
        {error && !!rows.length && (
          <p className="ad-hint" role="status">
            <Icon n="info" size={15} />
            <span>Could not reach the counter just now, so this is the last read.
              <button className="ad-link" onClick={reload}>Try again</button></span>
          </p>
        )}
        {loading && !rows.length && !error && <Empty icon="box" title="Loading…" text="Fetching the counter." />}

        {!!shown.length && (
          <ul className="ad-orders">
            <li className="ad-orders-head">
              <span>{shown.length} order{shown.length === 1 ? "" : "s"} at the counter</span>
            </li>
            {shown.map((row, i) => {
              const o = row.order || {};
              const stage = STAGE[row.counter] || { label: row.counter, tone: "grey" };
              return (
                <li key={row.job} style={{ "--i": i }}
                  className={"ad-order ad-order2" + (row.counter === "awaiting_shop" ? " ad-order-late" : "")}
                  onClick={(e) => { if (!e.target.closest("button,input,select,a") && o.ref) onOpenOrder?.(o.ref); }}>
                  <div className="ad-order2-main">
                    <div className="ad-order2-top">
                      <b>{o.customer?.name || row.customer}</b>
                      {o.customer?.area && <small>· {o.customer.area}</small>}
                      {row.channel && (
                        <span className={"ad-pill " + (row.channel === "whatsapp" ? "ad-t-green" : "ad-t-blue")}>
                          {row.channel === "whatsapp" ? "WhatsApp" : "Website"}
                        </span>
                      )}
                      {(o.customer?.tags || []).map((t) => <span key={t.id} className={"ad-pill ad-t-" + ROW_TONES[(t.color || 0) % ROW_TONES.length]}>{t.name}</span>)}
                    </div>
                    <small className="ad-order2-sub">
                      #{ref(row)} · <Icon n={row.kind === "quick" ? "bolt" : "truck"} size={12} /> {modeLabel(row.kind === "quick" ? "quick" : "all")}
                      {" "}· {row.lines.length} item{row.lines.length === 1 ? "" : "s"}{o.at ? ` · ${since(o.at)}` : ""}
                    </small>
                    <ul className="ad-counter-items">
                      {row.lines.map((l, k) => <li key={k}><b>{l.qty}</b> {l.name}</li>)}
                    </ul>
                    <div className="ad-order2-facts">
                      <span className={"ad-pill ad-t-" + stage.tone}>{stage.label}</span>
                      {row.waiting > 0 && row.counter === "awaiting_shop" && (
                        <span className="ad-late"><Icon n="clock" size={13} />waiting {row.waiting} min</span>
                      )}
                      <span className={"ad-order2-pay" + (!row.paid ? " ad-order2-cash" : "")}>
                        <Icon n={row.paid ? "check" : "cash"} size={13} />
                        {row.paid ? (o.method ? payText(o) : "Paid") : `Collect ${money(row.collect, o.currency)}`}
                      </span>
                      {row.rider && <span className="ad-order-pay">🛵 {row.rider}</span>}
                      {row.supplyWaiting && <span className="ad-waiting"><Icon n="clock" size={12} />Waiting for supplier stock</span>}
                      {row.pickupCode && <span className="ad-counter-code">Pickup code <b>{row.pickupCode}</b></span>}
                    </div>
                  </div>
                  <div className="ad-order2-side">
                    {o.total != null && <b>{money(o.total, o.currency)}</b>}
                    {row.counter === "awaiting_shop" && (
                      <button className="ad-btn ad-sm ad-primary" disabled={act.busy}
                        onClick={() => run(row, "accept", `#${ref(row)} accepted - pack it`)}>Accept<Icon n="right" size={13} /></button>
                    )}
                    {row.counter === "preparing" && !row.supplyWaiting && (
                      <>
                        <button className="ad-btn ad-sm ad-primary" disabled={act.busy}
                          onClick={() => run(row, "ready", `#${ref(row)} packed - rider called`)}>Packed – call the rider<Icon n="right" size={13} /></button>
                        <button className="ad-link" disabled={act.busy}
                          onClick={() => run(row, "unaccept", `#${ref(row)} put back`)}>Put back</button>
                      </>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        )}

        {!error && !loading && !shown.length && (
          <Empty icon="box"
            title={tab === "new" ? "No new orders" : "Nothing at the counter"}
            text={tab === "new"
              ? "New orders appear here on their own, with the alarm."
              : `Nothing open for ${tab === "quick" ? "Quick" : "Express"} delivery right now.`} />
        )}
      </section>
    </div>
  );
}
