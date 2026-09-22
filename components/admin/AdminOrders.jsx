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
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { money } from "@/lib/money";
import { useAction, useResource } from "@/lib/useFetch";
import { Avatar, Confirm, Drawer, Empty, Icon, Pill, Search, Select, Tabs } from "./AdminUI";
import { clock, dateShort, dateTime, overdueBy, since } from "./format";

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
  { tab: "packing", label: "Packed & shipped", icon: "layers", tone: "#f7931e" },
  { tab: "out", label: "Out", icon: "truck", tone: "#7b5cd6" },
  { tab: "late", label: "Late", icon: "clock", tone: "#c2410c", warn: true },
  { tab: "cash", label: "Cash to collect", icon: "cash", tone: "#1a7f3c", amount: true },
];

const PAGE = 20;
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

function OrderDrawer({ ref_, onClose, onAdvance, onCancel, reasons, busy, flash }) {
  const { data, loading, error, reload } = useResource(`/admin/orders/${encodeURIComponent(ref_)}`, {
    deps: [ref_],
  });
  const [confirm, setConfirm] = useState(false);
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
            {!o?.next && <button className="ad-btn ad-primary" onClick={close}>Close</button>}
          </>
        )}>

        {error && <Empty icon="info" title="We could not reach the shop" text={error.message}
          action="Try again" onAction={reload} />}
        {loading && !o && !error && <Empty icon="box" title="Loading…" text="Fetching the order." />}

        {o && (
          <>
            <div className="ad-drawer-top">
              <Pill s={o.state} map={STATUS} />
              {o.late && <span className="ad-late"><Icon n="clock" size={14} />{overdueBy(o.dueAt)}</span>}
              {o.eta && !o.late && <span className="ad-eta"><Icon n="clock" size={14} />{o.eta}</span>}
              <span className="ad-paid"><Icon n="cash" size={14} />{o.payNote || o.method || "—"}</span>
            </div>

            <section className="ad-dsec">
              <h4>Customer</h4>
              <div className="ad-person">
                <Avatar name={o.customer.name} tone="ad-a-blue" />
                <span>
                  <b>{o.customer.name}</b>
                  <small>{o.customer.phone || "No phone"} · {o.customer.orderCount} orders</small>
                </span>
                {o.customer.phone && (
                  <a className="ad-icon-btn" href={`tel:${o.customer.phone}`} aria-label="Call">
                    <Icon n="phone" size={16} />
                  </a>
                )}
              </div>
              <div className="ad-kv">
                <span className="ad-span2"><small>Deliver to</small>
                  {o.address
                    ? [o.address.line, o.address.area, o.address.city].filter(Boolean).join(", ")
                    : "No address on the order"}
                </span>
                <span><small>Slot</small>{o.slot || "—"}</span>
                <span><small>Promised</small>{o.dueAt ? dateTime(o.dueAt) : "—"}</span>
                {o.instructions && <span className="ad-span2"><small>Note</small>{o.instructions}</span>}
              </div>
            </section>

            {/* Not a rider. There is no rider model behind this console, and a
                dropdown that saves nowhere is worse than no dropdown. What is
                real is whether the customer has a door code and whether it has
                been used - which is what a manager actually rings about. */}
            <section className="ad-dsec">
              <h4>Delivery code</h4>
              <p className="ad-hint">
                <Icon n="info" size={14} />
                {!o.otp.issuedAt
                  ? "No code has been issued for this order yet."
                  : o.otp.usedAt
                    ? `Used at ${clock(o.otp.usedAt)} on ${dateShort(o.otp.usedAt)}.`
                    : `Issued ${clock(o.otp.issuedAt)}, not used yet. The customer has it in their app.`}
              </p>
            </section>

            <section className="ad-dsec">
              <h4>Items <em>{o.items.length}</em></h4>
              <ul className="ad-items">
                {o.items.map((l, i) => (
                  <li key={i}>
                    <span className="ad-qty-chip">{l.qty}×</span>
                    <span><b>{l.name}</b></span>
                    <b>{money(l.price * l.qty, o.currency)}</b>
                  </li>
                ))}
              </ul>
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
            </section>

            {!!o.returns.length && (
              <section className="ad-dsec">
                <h4>Returns <em>{o.returns.length}</em></h4>
                <ul className="ad-items">
                  {o.returns.map((r) => (
                    <li key={r.id}>
                      <span><b>{r.reason}</b><small>{r.kind === "replace" ? "Replacement" : "Refund"} · {r.state}</small></span>
                      <b>{r.amount ? money(r.amount, o.currency) : ""}</b>
                    </li>
                  ))}
                </ul>
                <p className="ad-hint"><Icon n="info" size={14} />
                  Returns are moved on in Odoo, under 369 Mart → Returns.
                </p>
              </section>
            )}

            <section className="ad-dsec"><h4>Progress</h4><Timeline o={o} /></section>
          </>
        )}
      </Drawer>

      {confirm && o && (
        <Confirm danger title={`Cancel order #${o.ref}?`} confirmLabel="Cancel order"
          text={
            <>
              {money(o.paid || o.bill.total, o.currency)} goes back the way it
              was paid{o.walletUsed ? ", wallet included" : ""}. The customer sees
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

export default function OrdersSection({ openId, setOpenId, query = "", flash }) {
  const [tab, setTab] = useState("needs");
  const [mode, setMode] = useState("");
  const [when, setWhen] = useState("all");
  const [sort, setSort] = useState("old");
  const [term, setTerm] = useState(query);
  const [q, setQ] = useState(query);
  const [sel, setSel] = useState([]);
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
    if (q) p.set("q", q);
    return "/admin/orders?" + p.toString();
  }, [tab, mode, when, sort, q, limit]);

  const { data, loading, error, reload } = useResource(path, { pollMs: 30000 });
  const counts = useResource("/admin/orders/counts", { pollMs: 30000 });
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
  const run = (fn, ok) =>
    act.run(async () => {
      await fn();
      await refresh();
      if (ok) flash?.(ok);
      return true;
    }).then((r) => {
      if (r === null) flash?.(act.error?.message || "That did not work.", "bad");
      return r;
    });

  const advance = (o) =>
    run(() => api(`/admin/orders/${encodeURIComponent(o.ref)}/advance`, { method: "POST" }),
      `#${o.ref} → ${(STATUS[o.next?.state]?.label || "moved on").toLowerCase()}`);

  const cancelOrder = (o, reason) =>
    run(() => api(`/admin/orders/${encodeURIComponent(o.ref)}/cancel`, {
      method: "POST", body: { reason },
    }), `#${o.ref} cancelled`);

  /* Sequenced, and one reload at the end. Firing N unawaited writes and
     reloading after the first is how a bulk action reports success for orders
     the shop refused. */
  const bulkAdvance = () =>
    act.run(async () => {
      const picked = rows.filter((o) => sel.includes(o.ref) && o.next);
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
      if (!failed.length) flash?.(`${done} order${done === 1 ? "" : "s"} moved on`);
      else flash?.(`${done} of ${picked.length} moved on. ${failed.join(", ")} did not.`, "bad");
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
            <Select value={sort} onChange={setSort} label="Sort"
              options={[["old", "Longest wait first"], ["new", "Newest first"], ["value", "Highest value"]]} />
            <button className="ad-btn" onClick={exportCsv} disabled={!rows.length}>
              <Icon n="download" size={16} />Export these
            </button>
          </div>
        </div>

        <div className={"ad-bulk" + (sel.length ? " ad-show" : "")}>
          <span><b>{sel.length}</b> selected</span>
          <button className="ad-btn ad-sm" onClick={bulkAdvance}
            disabled={act.busy || !shownSel.some((o) => o.next)}>Move all on</button>
          <button className="ad-link" onClick={() => setSel([])}>Clear</button>
        </div>

        {error && (
          <Empty icon="info" title="We could not reach the shop" text={error.message}
            action="Try again" onAction={reload} />
        )}
        {loading && !rows.length && !error && (
          <Empty icon="box" title="Loading…" text="Fetching orders." />
        )}

        {!error && !!rows.length && (
          <ul className="ad-orders">
            <li className="ad-orders-head">
              <input type="checkbox" checked={allShown} aria-label="Select all"
                onChange={(e) => setSel(e.target.checked ? rows.map((o) => o.ref) : [])} />
              <span>{total} order{total === 1 ? "" : "s"}{q ? ` matching “${q}”` : ""}</span>
            </li>
            {rows.map((o, i) => (
              <li key={o.ref} style={{ "--i": i % PAGE }}
                className={"ad-order" + (sel.includes(o.ref) ? " ad-selected" : "") + (o.late ? " ad-order-late" : "")}
                onClick={(e) => { if (!e.target.closest("button,input,select,a")) setOpenId(o.ref); }}>
                <input type="checkbox" checked={sel.includes(o.ref)} aria-label={`Select ${o.ref}`}
                  onChange={(e) => setSel((s) => (e.target.checked ? [...s, o.ref] : s.filter((x) => x !== o.ref)))} />

                <div className="ad-order-body">
                  <div className="ad-order-line1">
                    <span className="ad-order-id">
                      <Icon n={o.mode === "quick" ? "bolt" : "truck"} size={13}
                        className={o.mode === "quick" ? "hm-fill ad-q" : "ad-e"} />
                      #{o.ref}
                    </span>
                    <span className="ad-order-ago">{since(o.at)}</span>
                    <span className="ad-cell-person">
                      <Avatar name={o.customer.name} size={26}
                        tone={o.mode === "quick" ? "ad-a-blue" : "ad-a-orange"} />
                      <b>{o.customer.name}</b>
                      {o.customer.area && <small>· {o.customer.area}</small>}
                    </span>
                    <span className="ad-order-items">{o.itemCount} item{o.itemCount === 1 ? "" : "s"}</span>
                    <b className="ad-order-total">{money(o.total, o.currency)}</b>
                  </div>
                  <div className="ad-order-line2">
                    <Pill s={o.state} map={STATUS} />
                    {o.late
                      ? <span className="ad-late"><Icon n="clock" size={13} />{overdueBy(o.dueAt)}</span>
                      : <span className="ad-order-promise">{o.slot || o.eta || (o.dueAt ? `due ${clock(o.dueAt)}` : "")}</span>}
                    <span className="ad-order-pay">{o.payNote || o.method || "—"}</span>
                    <span className="ad-order-act">
                      {o.next && (
                        <button className="ad-btn ad-sm" disabled={act.busy}
                          onClick={() => advance(o)}>{o.next.label}</button>
                      )}
                      <button className="ad-icon-btn" aria-label={`Open ${o.ref}`}
                        onClick={() => setOpenId(o.ref)}><Icon n="right" size={16} /></button>
                    </span>
                  </div>
                </div>
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
          onAdvance={advance}
          onCancel={cancelOrder} />
      )}
    </div>
  );
}
