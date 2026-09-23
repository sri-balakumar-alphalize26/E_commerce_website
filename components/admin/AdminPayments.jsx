"use client";
/* ==========================================================================
   369 Mart admin — Payments

   Whether the money arrived, and if not, where it is.

   **Nothing on this screen writes anything, and that is the point.** A payment
   becomes true after the provider's own webhook has verified the signature; a
   button here that marked one paid would be a claim about money nobody
   received. The one settlement that happens away from a gateway is cash at the
   door, and it keeps its button in Odoo, pressed by somebody who knows whether
   the rider was handed the notes. Refunds belong to Returns.

   Three things the tiles are careful about, because each was wrong before:

     - **Money in today** follows the moment a payment became done, not the
       last time anything touched the row.
     - An order settled **entirely from the wallet** is not counted again; that
       money was counted when it was topped up.
     - **Settled** says what it is out of, because payments still waiting are
       not in the denominator.

   The twin of the Odoo desk at /odoo/mart-payments: both call
   `mart369_admin_list` on the model, so they cannot drift.
   ========================================================================== */
import { useEffect, useMemo, useState } from "react";
import { money } from "@/lib/money";
import { useResource } from "@/lib/useFetch";
import { Empty, Icon, Pill, Search, Select, Tabs } from "./AdminUI";
import { dateTime, since } from "./format";

/* Odoo's six states in the words a shopkeeper uses. `authorized` and `draft`
   keep their own pill rather than being folded into Paid: a payment a gateway
   is holding, and one the customer never submitted, are not money in. */
const STATES = {
  draft: { label: "Never sent", tone: "grey" },
  pending: { label: "Waiting", tone: "amber" },
  authorized: { label: "Held by the bank", tone: "violet" },
  done: { label: "Paid", tone: "green" },
  cancel: { label: "Cancelled", tone: "grey" },
  error: { label: "Failed", tone: "red" },
};

const KINDS = { order: "Order", topup: "Wallet top-up", validation: "Saving a card" };

export function PaymentsSection() {
  const [tab, setTab] = useState("all");
  const [kind, setKind] = useState("");
  const [term, setTerm] = useState("");
  const [q, setQ] = useState("");

  useEffect(() => {
    const id = setTimeout(() => setQ(term.trim()), 300);
    return () => clearTimeout(id);
  }, [term]);

  const path = useMemo(() => {
    const p = new URLSearchParams();
    if (tab !== "all") p.set("tab", tab);
    if (kind) p.set("kind", kind);
    if (q) p.set("q", q);
    const qs = p.toString();
    return "/admin/payments" + (qs ? `?${qs}` : "");
  }, [tab, kind, q]);

  /* Money moves while somebody is looking at this, so it polls faster than
     the screens where nothing changes on its own. `keepLast` so the rows do
     not blink out between polls. */
  const { data, loading, error, reload } = useResource(path, { pollMs: 30000, keepLast: true });

  const rows = data?.rows || [];
  const counts = data?.counts || {};
  const tiles = data?.tiles || {};
  const currency = tiles.currency;

  return (
    <div className="ad-stack">
      <section className="ad-mini-stats ad-pay-stats">
        <span>
          <small>Money in today</small>
          <b>{money(tiles.collected_amount ?? 0, currency)}</b>
          <i>
            {tiles.collected_count ?? 0} paid today
            {tiles.from_wallet_count
              ? `; ${tiles.from_wallet_count} more settled from wallets, counted at top-up`
              : ""}
          </i>
        </span>
        <span>
          <small>Settled</small>
          <b>{tiles.success_pct ?? 0}%</b>
          <i>of {tiles.success_of ?? 0} that finished</i>
        </span>
        <span className={tiles.pending ? "ad-warn" : ""}>
          <small>Waiting on a bank</small>
          <b>{tiles.pending ?? 0}</b>
          <i>{tiles.pending_oldest || "Nothing waiting"}</i>
        </span>
        <span>
          <small>Cash to collect</small>
          <b>{money(tiles.cash_amount ?? 0, currency)}</b>
          <i>{tiles.cash_count ?? 0} at the door</i>
        </span>
      </section>

      {/* Said once, so nobody hunts for a button that should not exist. */}
      <p className="ad-hint ad-readonly">
        <Icon n="info" size={14} />
        <span>
          Nothing here can be changed. A payment becomes paid when the bank
          confirms it, and cash is marked collected on the payment itself, by
          whoever took the notes. Refunds happen on the return.
        </span>
      </p>

      <section className="ad-card">
        <div className="ad-toolbar">
          <Tabs value={tab} onChange={setTab} tabs={[
            ["all", "All", counts.all ?? 0],
            ["paid", "Paid", counts.paid ?? 0],
            ["waiting", "Waiting on a bank", counts.waiting ?? 0],
            ["cash", "Cash to collect", counts.cash ?? 0],
            ["failed", "Failed", counts.failed ?? 0],
          ]} />
          <div className="ad-toolbar-right">
            <Search value={term} onChange={setTerm} placeholder="A reference, an order or a customer" />
            <Select value={kind} onChange={setKind} label="Kind"
              options={[["", "Orders and top-ups"], ["order", "Orders"], ["topup", "Top-ups"]]} />
          </div>
        </div>

        {error && (
          <Empty icon="info" title="We could not reach the shop" text={error.message}
            action="Try again" onAction={reload} />
        )}
        {loading && !rows.length && !error && (
          <Empty icon="card" title="Loading…" text="Fetching payments." />
        )}
        {!error && !loading && !rows.length && (
          <Empty icon="card"
            title={tab === "failed" ? "Nothing has failed" : "No payment here"}
            text={tab === "failed"
              ? "That is the good version of this tab being empty."
              : q || tab !== "all" || kind
                ? "Nothing matches that. Try another tab, or clear the search."
                : "Payments appear here as customers pay in the app."} />
        )}

        {!error && !!rows.length && (
          <ul className="ad-pays">
            {rows.map((r, i) => (
              <li key={r.id} style={{ "--i": i }}>
                <div className="ad-pay-body">
                  <div className="ad-pay-top">
                    <b>{r.customer || "A customer"}</b>
                    <Pill s={r.state} map={STATES} />
                    {r.cod && r.state === "pending" && (
                      <span className="ad-pill ad-t-blue"><i />At the door</span>
                    )}
                    <small>
                      {KINDS[r.kind] || r.kind}
                      {r.method ? ` · ${r.method}` : ""}
                      {r.provider ? ` (${r.provider})` : ""}
                      {r.at ? <> {" · "}<span title={dateTime(r.at)}>{since(r.at)}</span></> : null}
                    </small>
                  </div>
                  <p className="ad-pay-sub">
                    <code>{r.ref}</code>
                    {r.orderRef ? <> {" · "}{r.orderRef}</> : null}
                    {r.message ? <> {" · "}<span className="ad-pay-why">{r.message}</span></> : null}
                  </p>
                </div>
                <div className="ad-pay-worth">
                  <b>{money(r.amount, r.currency || currency)}</b>
                  {r.walletUsed
                    ? <small>and {money(r.walletUsed, r.currency || currency)} from the wallet</small>
                    : null}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
