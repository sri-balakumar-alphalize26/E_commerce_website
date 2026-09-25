"use client";
/* ==========================================================================
   369 Mart — Admin · Returns

   A queue, the same shape as Orders: five tiles that are the filter, oldest
   first, one next-step button per row labelled by the server, and a drawer
   with everything about one return.

   Returns already worked everywhere except here. The model moves them
   (`requested → pickup → picked → done`, plus `refused`), the app can request
   one, and Odoo's own kanban can process one. The console could only show a
   count and a read-only list inside an order, under a hint telling staff to go
   and do it in Odoo. This is that screen.

   Two rules carried over from Orders, both load-bearing:

   - The browser never works out what happens next. `row.next.label` and the
     drawer's `flow` come from the server, so the button's words cannot drift
     from what pressing it does.
   - Refuse is hidden, not disabled, when the server says `canRefuse` is false
     — because the model refuses a refusal once the money has gone back, and a
     button that exists only to say no is worse than no button.

   And one rule of its own: **it never says "Refunded" flatly.** The model puts
   back the wallet leg and deliberately leaves gateway money to the gateway, so
   the drawer shows the split. An operator who reads "refunded", closes the
   ticket and leaves the customer out of pocket is the bug this screen exists
   not to cause.
   ========================================================================== */
import { useEffect, useMemo, useState } from "react";

import { api } from "@/lib/api";
import { useResource, useAction } from "@/lib/useFetch";
import { Avatar, Confirm, Drawer, Empty, Icon, Pill, Search, Select, Tabs } from "./AdminUI";
import { dateTime, since } from "./format";
import { money } from "@/lib/money";
import "./admin.css";

const PAGE = 25;

/* The vocabulary, for `Pill`. Tones follow the orders board: blue while it is
   somebody's problem, green when it is finished, red when it was refused. */
const STATUS = {
  requested: { label: "Requested", tone: "blue" },
  pickup: { label: "Pickup scheduled", tone: "amber" },
  picked: { label: "Picked up", tone: "violet" },
  done: { label: "Refund issued", tone: "green" },
  refused: { label: "Refused", tone: "red" },
};

const KIND = { refund: "Refund", replace: "Replacement" };

const TABS = [
  ["needs", "Needs me", "needs"],
  ["all", "All", null],
  ["done", "Refunded", null],
  ["refused", "Refused", null],
];

/* Each tile sets the tab, so the strip is the filter row rather than a
   decoration above one. */
const TILES = [
  { tab: "requested", label: "Requested", icon: "box", tone: "#0a78ab" },
  { tab: "pickup", label: "Pickup scheduled", icon: "truck", tone: "#b7791f" },
  { tab: "picked", label: "Picked up", icon: "check", tone: "#7b5cd6" },
  { tab: "done", label: "Refunded", icon: "cash", tone: "#1a7f3c" },
  { tab: "refused", label: "Refused", icon: "x", tone: "#c8433a" },
];

function Tiles({ counts, tab, onPick }) {
  return (
    <div className="ad-stats ad-order-tiles">
      {TILES.map((t, i) => (
        <button
          key={t.tab}
          className={"ad-stat ad-stat-btn" + (tab === t.tab ? " ad-stat-on" : "")}
          aria-pressed={tab === t.tab}
          style={{ "--i": i }}
          onClick={() => onPick(t.tab)}
        >
          <header>
            <span className="ad-stat-ic" style={{ "--tone": t.tone }}>
              <Icon n={t.icon} size={16} />
            </span>
            {t.label}
          </header>
          <b>{counts?.[t.tab] ?? "—"}</b>
          <div className="ad-stat-foot"><small>Tap to filter</small></div>
        </button>
      ))}
    </div>
  );
}

/* Where the return has got to, drawn off the server's own ladder. A refused
   return left the ladder, so it is said rather than drawn. */
function Timeline({ d }) {
  if (d.state === "refused") {
    return <p className="ad-hint">This return was refused, so it never went any further.</p>;
  }
  const at = d.flow.findIndex((s) => s.state === d.state);
  const finished = at === d.flow.length - 1;
  /* Drawn like the order's progress: a ticked dot for each step reached, the
     one it is at marked "Now", the rest greyed out. */
  return (
    <ol className="ad-timeline">
      {d.flow.map((s, i) => {
        const reached = i <= at;
        const now = i === at && !finished;
        return (
          <li key={s.state} className={(reached ? "ad-done" : "ad-next") + (now ? " ad-now" : "")} style={{ "--i": i }}>
            <i>{reached ? <Icon n="check" size={11} /> : null}</i>
            <span><b>{s.label}</b><small>{now ? "Now" : reached ? "Done" : "Next"}</small></span>
          </li>
        );
      })}
    </ol>
  );
}

/* What pressing "Issue refund" does: the whole refund goes to the customer's
   369 Wallet at once, however they paid, never more than they are still owed
   (an item already taken out or an earlier return is not refunded twice). */
function Refund({ r, currency }) {
  if (!r || !r.total) return null;
  return (
    <div className="ad-bill">
      <div className="ad-bill-total"><span>To the customer's 369 Wallet</span><b>{money(r.wallet, currency)}</b></div>
      <p className="ad-hint">
        Paid by {r.method || "card"} or not, the whole refund goes to the 369 Wallet the moment it is issued,
        with a credit note for the books.
        {r.wallet < r.total ? ` ${money(r.total - r.wallet, currency)} of it was already given back.` : ""}
      </p>
    </div>
  );
}

function Photos({ id, ids }) {
  if (!ids?.length) {
    return <p className="ad-hint">The customer sent no photos with this one.</p>;
  }
  return (
    <div className="ad-rt-photos">
      {ids.map((p) => (
        <a key={p} href={`/api/mart/admin/returns/${id}/photo/${p}`}
           target="_blank" rel="noreferrer" title="Open full size">
          <img src={`/api/mart/admin/returns/${id}/photo/${p}`} alt="" loading="lazy" />
        </a>
      ))}
    </div>
  );
}

/* Uses AdminUI's own Drawer rather than a second one: the portal, the escape
   key, the scroll lock and the closing animation are all already there. */
function ReturnDrawer({ id, onClose, onAdvance, onRefuse, busy }) {
  const { data, loading, error, reload } = useResource(`/admin/returns/${id}`, { deps: [id] });
  const [confirm, setConfirm] = useState(null);
  const d = data;

  /* Read-after-write inside the drawer too, so the ladder and the buttons
     redraw from the server rather than from a guess. */
  const act = async (fn) => { const ok = await fn(); if (ok) await reload(); return ok; };

  return (
    <Drawer
      wide
      title={d ? `Return on #${d.ref}` : "Return"}
      sub={d ? `${dateTime(d.at)} · ${KIND[d.kind] || d.kind}` : ""}
      onClose={onClose}
      foot={d ? (close) => (
        <>
          <button className="ad-btn" onClick={close}>Close</button>
          {/* Hidden, not disabled: the model refuses a refusal once the refund
              has gone, so there is nothing to offer. */}
          {d.canRefuse && (
            <button className="ad-btn ad-danger-ghost" disabled={busy}
              onClick={() => setConfirm(true)}>Refuse</button>
          )}
          {d.next && (
            <button className="ad-btn ad-primary" disabled={busy}
              onClick={() => act(() => onAdvance(d))}>{d.next.label}</button>
          )}
        </>
      ) : null}
    >
      {error && (
        <Empty icon="info" title="We could not reach the shop"
          text={error.message} action="Try again" onAction={reload} />
      )}
      {loading && !d && <Empty icon="box" title="Loading…" text="Fetching the return." />}

      {d && (
        <>
          <div className="ad-drawer-top">
            <Pill s={d.state} map={STATUS} />
            <span className="ad-eta">{since(d.at)}</span>
          </div>

          <section className="ad-dsec">
            <h4>Customer</h4>
            {/* A span, not a div: .ad-person stacks the name over the phone
                with `> span:nth-child(2)`, so a div runs them together. */}
            <div className="ad-person ad-person-lg">
              <Avatar name={d.who} tone="ad-a-blue" />
              <span>
                <b>{d.who}</b>
                <small>{d.phone || "No phone"}</small>
              </span>
            </div>
          </section>

          <section className="ad-dsec">
            <h4>Why</h4>
            <div className="ad-kv"><span>Reason</span><b>{d.reason || "—"}</b></div>
            <div className="ad-kv"><span>Wants</span><b>{KIND[d.kind] || d.kind}</b></div>
            {/* Prose, because it is prose: the app flattens the chosen items
                and the pickup slot into this one string. */}
            {d.detail && <p className="ad-hint ad-span2">{d.detail}</p>}
          </section>

          <section className="ad-dsec">
            <h4>Photos {d.photos > 0 && <em>{d.photos}</em>}</h4>
            <Photos id={d.id} ids={d.photoIds} />
          </section>

          <section className="ad-dsec">
            <h4>The money</h4>
            <Refund r={d.refund} currency={d.currency} />
          </section>

          <section className="ad-dsec">
            <h4>The order</h4>
            <div className="ad-kv"><span>Number</span><b>#{d.order.ref}</b></div>
            <div className="ad-kv"><span>Order total</span><b>{money(d.order.total, d.currency)}</b></div>
          </section>

          <section className="ad-dsec">
            <h4>Progress</h4>
            <Timeline d={d} />
          </section>
        </>
      )}

      {confirm && (
        <Confirm
          danger
          title="Refuse this return?"
          text="The customer is told it was refused, and it stops here. Nothing is refunded."
          confirmLabel="Refuse it"
          onCancel={() => setConfirm(null)}
          onConfirm={() => { act(() => onRefuse(d)); setConfirm(null); }}
        />
      )}
    </Drawer>
  );
}

export default function ReturnsSection({ flash }) {
  const [tab, setTab] = useState("needs");
  const [kind, setKind] = useState("");
  const [sort, setSort] = useState("old");
  const [term, setTerm] = useState("");
  const [q, setQ] = useState("");
  const [limit, setLimit] = useState(PAGE);
  const [open, setOpen] = useState(null);

  /* Searched on the server, so the box is debounced rather than filtering a
     list the browser happens to be holding. */
  useEffect(() => {
    const id = setTimeout(() => { setQ(term.trim()); setLimit(PAGE); }, 300);
    return () => clearTimeout(id);
  }, [term]);

  const path = useMemo(() => {
    const p = new URLSearchParams({ tab, sort, limit: String(limit) });
    if (kind) p.set("kind", kind);
    if (q) p.set("q", q);
    return "/admin/returns?" + p.toString();
  }, [tab, kind, sort, q, limit]);

  const { data, loading, error, reload } = useResource(path, { pollMs: 30000, keepLast: true });
  const act = useAction();

  const rows = data?.returns || [];
  const total = data?.total || 0;
  const counts = data?.counts;

  const refresh = async () => { api.invalidate("/admin/returns"); await reload(); };

  /* Read-after-write. `next`, `canRefuse` and the tile numbers are all the
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

  const advance = (r) =>
    run(() => api(`/admin/returns/${r.id}/advance`, { method: "POST" }),
      `#${r.ref} → ${(r.next?.label || "moved on").toLowerCase()}`);

  const refuse = (r) =>
    run(() => api(`/admin/returns/${r.id}/refuse`, { method: "POST" }),
      `#${r.ref} refused`);

  return (
    <div className="ad-stack">
      <Tiles counts={counts} tab={tab} onPick={setTab} />

      <section className="ad-card">
        <div className="ad-toolbar">
          <Tabs tabs={TABS.map(([k, l, c]) => [k, l, c ? counts?.[c] : null])}
            value={tab} onChange={setTab} />
          <div className="ad-toolbar-right">
            <Search value={term} onChange={setTerm} placeholder="Order, customer or reason" />
            <Select value={kind} onChange={setKind} label="Wants"
              options={[["", "Refund or replacement"], ["refund", "Refund"], ["replace", "Replacement"]]} />
            <Select value={sort} onChange={setSort} label="Sort"
              options={[["old", "Oldest first"], ["new", "Newest first"]]} />
          </div>
        </div>

        {error && !rows.length && (
          <Empty icon="info" title="We could not reach the shop"
            text={error.message} action="Try again" onAction={reload} />
        )}
        {error && !!rows.length && (
          <p className="ad-hint" role="status">
            <Icon n="info" size={15} />
            <span>Could not reach the shop just now, so this is the last read.
              <button className="ad-link" onClick={reload}>Try again</button></span>
          </p>
        )}

        {/* The rows stay on screen while the next page loads: a queue that
            blanks on every filter feels broken. */}
        {loading && !rows.length && !error && (
          <Empty icon="box" title="Loading…" text="Fetching the queue." />
        )}

        {!!rows.length && (
          <ul className="ad-orders">
            <li className="ad-orders-head">
              <span>{total} return{total === 1 ? "" : "s"}{q ? ` matching “${q}”` : ""}</span>
            </li>
            {rows.map((r, i) => (
              <li key={r.id} className="ad-order" style={{ "--i": i % PAGE }}
                onClick={(e) => { if (!e.target.closest("button,a")) setOpen(r.id); }}>
                <div className="ad-order-body">
                  <div className="ad-order-line1">
                    <b className="ad-order-id">#{r.ref}</b>
                    <span className="ad-order-ago">{since(r.at)}</span>
                    <span className="ad-cell-person">{r.who}</span>
                    {r.photos > 0 && (
                      <span className="ad-qty-chip" title="Photos from the customer">
                        <Icon n="note" size={12} /> {r.photos}
                      </span>
                    )}
                  </div>
                  <div className="ad-order-line2">
                    <Pill s={r.state} map={STATUS} />
                    <span>{KIND[r.kind] || r.kind}</span>
                    <span className="ad-order-total">{money(r.amount, r.currency)}</span>
                    <span className="ad-order-promise">{r.reason}</span>
                  </div>
                </div>
                <div className="ad-order-act">
                  {r.next && (
                    <button className="ad-btn ad-sm" disabled={act.busy}
                      onClick={() => advance(r)}>
                      {r.next.label}
                    </button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}

        {!error && !loading && !rows.length && (
          <Empty icon="box" title="Nothing here"
            text={tab === "needs"
              ? "No return is waiting on anybody. That is the queue empty, not broken."
              : "No return matches that."} />
        )}

        {rows.length < total && (
          <div className="ad-more">
            <button className="ad-btn" disabled={loading}
              onClick={() => setLimit((l) => l + PAGE)}>Show more</button>
          </div>
        )}
      </section>

      {open && (
        <ReturnDrawer id={open} busy={act.busy} onClose={() => setOpen(null)}
          onAdvance={advance} onRefuse={refuse} />
      )}
    </div>
  );
}
