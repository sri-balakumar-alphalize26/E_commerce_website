"use client";
/* ==========================================================================
   369 Mart admin — Orders
   Toolbar (status tabs, mode, sort, export) · bulk actions · table ·
   order drawer (customer, delivery, items, bill, timeline, actions).
   ========================================================================== */
import { useMemo, useState } from "react";
import { Avatar, Confirm, Drawer, Empty, Icon, Pill, Search, Select, Tabs } from "./AdminUI";
import { FLOW, NEXT_LABEL, RIDERS, STATUS, TODAY, clock, dateShort, dateTime, inr, istMidnight, since } from "./adminData";

const CANCEL_REASONS = ["Item out of stock", "Customer asked to cancel", "Address not reachable", "Payment not confirmed", "Store closed"];
const PAGE = 12;

function Timeline({ o }) {
  const at = FLOW.indexOf(o.status);
  const step = (k, i) => {
    const done = o.status === "cancelled" ? i === 0 : i <= at;
    const t = o.at + i * 7 * 60000;
    return (
      <li key={k} className={(done ? "ad-done" : "") + (i === at && o.status !== "delivered" ? " ad-now" : "")} style={{ "--i": i }}>
        <i>{done ? <Icon n="check" size={11} /> : null}</i>
        <span><b>{STATUS[k].label}</b><small>{done ? clock(t) : "Pending"}</small></span>
      </li>
    );
  };
  return (
    <ol className="ad-timeline">
      {FLOW.map(step)}
      {o.status === "cancelled" && (
        <li className="ad-done ad-cancelled" style={{ "--i": 1 }}><i><Icon n="x" size={11} /></i><span><b>Cancelled</b><small>{o.cancelReason || "By store"}</small></span></li>
      )}
    </ol>
  );
}

function OrderDrawer({ o, onClose, advance, assign, cancelOrder, flash }) {
  const [confirm, setConfirm] = useState(false);
  const [reason, setReason] = useState(CANCEL_REASONS[0]);
  const open = o.status !== "delivered" && o.status !== "cancelled";
  return (
    <>
      <Drawer title={`Order #${o.id}`} sub={`${dateTime(o.at)} · ${o.mode === "quick" ? "Quick" : "Express"}`} onClose={onClose} wide
        foot={(close) => (
          <>
            <button className="ad-btn" onClick={() => flash("Invoice sent to the printer")}><Icon n="printer" size={16} />Invoice</button>
            {open && <button className="ad-btn ad-danger-ghost" onClick={() => setConfirm(true)}>Cancel order</button>}
            {NEXT_LABEL[o.status] && <button className="ad-btn ad-primary" onClick={() => advance(o.id)}>{NEXT_LABEL[o.status]}<Icon n="right" size={15} /></button>}
            {!open && <button className="ad-btn ad-primary" onClick={close}>Close</button>}
          </>
        )}>
        <div className="ad-drawer-top"><Pill s={o.status} />{o.eta && open && <span className="ad-eta"><Icon n="clock" size={14} />ETA {o.eta} min</span>}<span className="ad-paid"><Icon n="cash" size={14} />{o.pay}</span></div>

        <section className="ad-dsec">
          <h4>Customer</h4>
          <div className="ad-person">
            <Avatar name={o.customer.name} tone="ad-a-blue" />
            <span><b>{o.customer.name}</b><small>{o.customer.phone} · {o.customer.orders} orders</small></span>
            <button className="ad-icon-btn" aria-label="Call" onClick={() => flash(`Calling ${o.customer.name}`)}><Icon n="phone" size={16} /></button>
            <button className="ad-icon-btn" aria-label="Chat" onClick={() => flash("Chat opened")}><Icon n="chat" size={16} /></button>
          </div>
          <div className="ad-kv">
            <span><small>Delivery area</small>{o.customer.area}, Kochi</span>
            <span><small>Slot</small>{o.slot}</span>
            {o.note && <span className="ad-span2"><small>Note</small>{o.note}</span>}
          </div>
        </section>

        <section className="ad-dsec">
          <h4>Rider</h4>
          <div className="ad-rider-pick">
            <Select value={o.rider?.id || ""} onChange={(v) => assign(o.id, v)} label="Rider"
              options={[["", "Not assigned"], ...RIDERS.map((r) => [r.id, `${r.name} · ${r.vehicle}`])]} />
            {o.rider && <span className="ad-ok"><Icon n="check" size={14} />{o.rider.name} on the way</span>}
          </div>
        </section>

        <section className="ad-dsec">
          <h4>Items <em>{o.items.length}</em></h4>
          <ul className="ad-items">
            {o.items.map((l) => (
              <li key={l.id}><span className="ad-qty-chip">{l.qty}×</span><span><b>{l.name}</b><small>{l.unit}</small></span><b>{inr(l.price * l.qty)}</b></li>
            ))}
          </ul>
          <dl className="ad-bill">
            <div><dt>Items</dt><dd>{inr(o.sub)}</dd></div>
            <div><dt>Delivery</dt><dd>{o.fee ? inr(o.fee) : "Free"}</dd></div>
            <div className="ad-bill-total"><dt>Total</dt><dd>{inr(o.total)}</dd></div>
          </dl>
        </section>

        <section className="ad-dsec"><h4>Progress</h4><Timeline o={o} /></section>
      </Drawer>
      {confirm && (
        <Confirm danger title={`Cancel order #${o.id}?`} confirmLabel="Cancel order"
          text={<>The customer is refunded {inr(o.total)} to {o.pay.includes("Cash") ? "369 Wallet" : o.pay}.<br /><select className="ad-reason" value={reason} onChange={(e) => setReason(e.target.value)}>{CANCEL_REASONS.map((r) => <option key={r}>{r}</option>)}</select></>}
          onCancel={() => setConfirm(false)} onConfirm={() => { setConfirm(false); cancelOrder(o.id, reason); onClose(); }} />
      )}
    </>
  );
}

export default function OrdersSection({ orders, openId, setOpenId, advance, assign, cancelOrder, flash }) {
  const [tab, setTab] = useState("live");
  const [mode, setMode] = useState("all");
  const [when, setWhen] = useState("today");
  const [sort, setSort] = useState("new");
  const [q, setQ] = useState("");
  const [sel, setSel] = useState([]);
  const [page, setPage] = useState(1);

  const matchTab = (o) => tab === "all" || (tab === "live" ? ["new", "packing", "ready", "out"].includes(o.status) : o.status === tab);
  const rows = useMemo(() => {
    const term = q.trim().toLowerCase();
    const from = when === "today" ? istMidnight(TODAY) : when === "7d" ? TODAY - 7 * 86400000 : 0;
    return orders
      .filter((o) => matchTab(o)
        && (mode === "all" || (mode === "quick" ? o.mode === "quick" : o.mode === "all"))
        && o.at >= from
        && (!term || (o.id + " " + o.customer.name + " " + o.customer.area + " " + o.items.map((i) => i.name).join(" ")).toLowerCase().includes(term)))
      .sort((a, b) => (sort === "new" ? b.at - a.at : sort === "old" ? a.at - b.at : b.total - a.total));
  }, [orders, tab, mode, when, sort, q]); // eslint-disable-line
  const shown = rows.slice(0, page * PAGE);
  const open = orders.find((o) => o.id === openId);
  const count = (s) => orders.filter((o) => (s === "live" ? ["new", "packing", "ready", "out"].includes(o.status) : o.status === s)).length;

  const exportCsv = () => {
    const head = ["Order", "Placed", "Mode", "Customer", "Area", "Items", "Total", "Payment", "Status", "Rider"];
    const body = rows.map((o) => [o.id, dateTime(o.at), o.mode === "quick" ? "Quick" : "Express", o.customer.name, o.customer.area, o.items.length, o.total, o.pay, STATUS[o.status].label, o.rider?.name || ""]);
    const csv = [head, ...body].map((r) => r.map((c) => `"${String(c).replace(/"/g, '""')}"`).join(",")).join("\n");
    try {
      const url = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
      const a = document.createElement("a"); a.href = url; a.download = `369mart-orders-${dateShort(TODAY).replace(/ /g, "-")}.csv`; a.click();
      URL.revokeObjectURL(url);
      flash(`${rows.length} orders exported`);
    } catch (e) { flash("Export failed", "bad"); }
  };
  const bulkAdvance = () => { sel.forEach(advance); flash(`${sel.length} orders moved on`); setSel([]); };
  const allShown = shown.length > 0 && shown.every((o) => sel.includes(o.id));

  return (
    <div className="ad-stack">
      <section className="ad-card">
        <div className="ad-toolbar">
          <Tabs value={tab} onChange={(v) => { setTab(v); setPage(1); }} tabs={[["live", "Live", count("live")], ["new", "New", count("new")], ["out", "Out", count("out")], ["delivered", "Delivered"], ["cancelled", "Cancelled"], ["all", "All"]]} />
          <div className="ad-toolbar-right">
            <Search value={q} onChange={(v) => { setQ(v); setPage(1); }} placeholder="Order id, customer, item" />
            <Select value={mode} onChange={(v) => { setMode(v); setPage(1); }} label="Type" options={[["all", "All types"], ["quick", "Quick"], ["express", "Express"]]} />
            <Select value={when} onChange={(v) => { setWhen(v); setPage(1); }} label="Period" options={[["today", "Today"], ["7d", "Last 7 days"], ["all", "All time"]]} />
            <Select value={sort} onChange={setSort} label="Sort" options={[["new", "Newest first"], ["old", "Oldest first"], ["value", "Highest value"]]} />
            <button className="ad-btn" onClick={exportCsv}><Icon n="download" size={16} />Export</button>
          </div>
        </div>

        <div className={"ad-bulk" + (sel.length ? " ad-show" : "")}>
          <span><b>{sel.length}</b> selected</span>
          <button className="ad-btn ad-sm" onClick={bulkAdvance}>Move to next step</button>
          <button className="ad-btn ad-sm" onClick={() => { flash(`${sel.length} labels printed`); setSel([]); }}><Icon n="printer" size={15} />Print labels</button>
          <button className="ad-link" onClick={() => setSel([])}>Clear</button>
        </div>

        <div className="ad-table-wrap">
          <table className="ad-table">
            <thead>
              <tr>
                <th className="ad-check"><input type="checkbox" checked={allShown} onChange={(e) => setSel(e.target.checked ? shown.map((o) => o.id) : [])} aria-label="Select all" /></th>
                <th>Order</th><th>Customer</th><th className="ad-num">Items</th><th className="ad-num">Total</th><th>Payment</th><th>Status</th><th>Rider</th><th className="ad-num">Placed</th><th />
              </tr>
            </thead>
            <tbody>
              {shown.map((o, i) => (
                <tr key={o.id} style={{ "--i": i % PAGE }} className={sel.includes(o.id) ? "ad-selected" : ""} onClick={(e) => { if (!e.target.closest("button,input,select")) setOpenId(o.id); }}>
                  <td className="ad-check"><input type="checkbox" checked={sel.includes(o.id)} onChange={(e) => setSel((s) => (e.target.checked ? [...s, o.id] : s.filter((x) => x !== o.id)))} aria-label={`Select ${o.id}`} /></td>
                  <td><span className="ad-order-id"><Icon n={o.mode === "quick" ? "bolt" : "truck"} size={13} className={o.mode === "quick" ? "hm-fill ad-q" : "ad-e"} />#{o.id}</span></td>
                  <td>
                    <span className="ad-cell-person"><Avatar name={o.customer.name} size={30} tone={o.mode === "quick" ? "ad-a-blue" : "ad-a-orange"} />
                      <span><b>{o.customer.name}</b><small>{o.customer.area}</small></span></span>
                  </td>
                  <td className="ad-num">{o.items.length}</td>
                  <td className="ad-num ad-strong">{inr(o.total)}</td>
                  <td><small>{o.pay}</small></td>
                  <td><Pill s={o.status} /></td>
                  <td>{o.rider ? <small>{o.rider.name}</small> : <small className="ad-dim">—</small>}</td>
                  <td className="ad-num"><span className="ad-when"><b>{clock(o.at)}</b><small>{since(o.at)}</small></span></td>
                  <td className="ad-row-act">
                    {NEXT_LABEL[o.status] && <button className="ad-btn ad-sm" onClick={() => advance(o.id)}>{NEXT_LABEL[o.status]}</button>}
                    <button className="ad-icon-btn" onClick={() => setOpenId(o.id)} aria-label={`Open ${o.id}`}><Icon n="right" size={16} /></button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!rows.length && <Empty icon="box" title="No orders here" text="Try another tab, period or search." />}
        </div>
        {shown.length < rows.length && (
          <div className="ad-more"><button className="ad-btn" onClick={() => setPage((p) => p + 1)}>Show more ({rows.length - shown.length} left)</button></div>
        )}
      </section>

      {open && <OrderDrawer o={open} onClose={() => setOpenId(null)} advance={advance} assign={assign} cancelOrder={cancelOrder} flash={flash} />}
    </div>
  );
}
