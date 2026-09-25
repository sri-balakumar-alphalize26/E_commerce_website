"use client";
/* ==========================================================================
   369 Mart admin — Addresses

   Where customers' shopping is sent. The screen exists so somebody on the
   phone can answer "why did this not arrive" — a missing pincode, no mobile
   number, no map pin.

   **Read-only, on purpose.** These are other people's home addresses, and the
   address a customer has marked as theirs is what Odoo ships to. Nothing here
   edits or deletes one, and there is no route behind such a thing either. So
   unlike the writing sections this file has no `run()` helper and no
   `Confirm`: there is nothing to write. A customer edits their own addresses
   in the app.

   The gap tiles count raw fields rather than the "missing pincode, mobile"
   label the backend shows in red — that label is worked out on the fly and
   cannot be searched or counted.
   ========================================================================== */
import { useEffect, useMemo, useState } from "react";
import { useResource } from "@/lib/useFetch";
import { Avatar, Empty, Icon, Search, Tabs } from "./AdminUI";
import { CustomerDrawer } from "./AdminCatalog";

const PAGE = 30;

/* What is still owed attention first. */
const TABS = [
  ["all", "All"],
  ["no_pincode", "No pincode"],
  ["no_mobile", "No mobile"],
  ["no_location", "No map pin"],
  ["archived", "Removed"],
];

export function AddressesSection({ flash }) {
  const [tab, setTab] = useState("all");
  const [term, setTerm] = useState("");
  const [q, setQ] = useState("");
  const [limit, setLimit] = useState(PAGE);
  // Customers whose addresses are showing, by customerId. Survives the poll
  // and tab changes, so an open row never snaps shut.
  const [open, setOpen] = useState({});
  // The customer whose details drawer is up - the same drawer Customers uses.
  const [viewing, setViewing] = useState(null);

  useEffect(() => {
    const id = setTimeout(() => { setQ(term.trim()); setLimit(PAGE); }, 300);
    return () => clearTimeout(id);
  }, [term]);

  const path = useMemo(() => {
    const p = new URLSearchParams({ tab, limit: String(limit) });
    if (q) p.set("q", q);
    return "/admin/addresses?" + p.toString();
  }, [tab, q, limit]);

  /* `keepLast` because this polls: without it one failed tick empties the list
     and the next good tick replays every row's entrance. */
  const { data, loading, error, reload } = useResource(path, { pollMs: 60000, keepLast: true });

  const rows = data?.addresses || [];
  const counts = data?.counts || {};
  const total = data?.total || 0;

  const groups = useMemo(() => {
    const out = [];
    for (const a of rows) {
      const last = out[out.length - 1];
      if (last && last.key === a.customerId) last.rows.push(a);
      else out.push({ key: a.customerId, customer: a.customer, user: a.customerUser,
                      total: a.customerTotal || 1, rows: [a] });
    }
    for (const g of out) g.gaps = g.rows.some((a) => a.gaps?.length);
    return out;
  }, [rows]);

  return (
    <div className="ad-stack">
      <section className="ad-mini-stats">
        <span><small>Addresses</small><b>{counts.all ?? 0}</b></span>
        <span><small>Customers</small><b>{data?.customers ?? 0}</b></span>
        <span className="ad-warn"><small>Missing something</small><b>{data?.incomplete ?? 0}</b></span>
        <span><small>No map pin</small><b>{counts.no_location ?? 0}</b></span>
      </section>

      <section className="ad-card">
        <div className="ad-toolbar">
          <Tabs value={tab} onChange={(v) => { setTab(v); setLimit(PAGE); }}
            tabs={TABS.map(([k, label]) => [k, label, counts[k] ?? null])} />
          <div className="ad-toolbar-right">
            <Search value={term} onChange={setTerm} placeholder="Customer, area or pincode" />
          </div>
        </div>

        {error && <Empty icon="info" title="We could not reach the shop"
          text={error.message} action="Try again" onAction={reload} />}
        {loading && !rows.length && !error && (
          <Empty icon="pin" title="Loading…" text="Fetching addresses." />
        )}

        {!error && !!rows.length && (
          /* One row per customer, closed until tapped - "Ravi, 3 addresses ›".
             The server sorts by customer, the default first, so neighbours
             group; a search opens every group so a match is never hidden. */
          <ul className="ad-owners">
            {groups.map((g, i) => {
              const expanded = !!q || !!open[g.key];
              return (
                <li key={g.key} style={{ "--i": i }} className={expanded ? "ad-owner ad-owner-open" : "ad-owner"}>
                  {/* The row takes the click, so the chevron beyond View full profile toggles
                      too; the button stops it. */}
                  <div className="ad-owner-headrow" onClick={() => setOpen((o) => ({ ...o, [g.key]: !o[g.key] }))}>
                    <button type="button" className="ad-owner-head" aria-expanded={expanded}>
                      <span className="ad-owner-sno">{i + 1}</span>
                      <Avatar name={g.customer} size={38} tone={g.gaps ? "ad-a-orange" : "ad-a-blue"} />
                      <b>{g.customer}</b>
                      <small>
                        {g.total} address{g.total === 1 ? "" : "es"}
                        {g.rows.length < g.total ? ` · ${g.rows.length} on this page` : ""}
                      </small>
                      {g.gaps && <span className="ad-owner-warn" title="Missing something"><Icon n="info" size={15} /></span>}
                    </button>
                    {g.user && (
                      <button type="button" className="ad-btn ad-sm ad-owner-view"
                        onClick={(e) => { e.stopPropagation(); setViewing({ id: g.user, name: g.customer }); }}>
                        <Icon n="users" size={14} /> View full profile
                      </button>
                    )}
                    <span className="ad-owner-chev"><Icon n="chev" size={16} /></span>
                  </div>
                  {expanded && (
                    <div className="ad-owner-body">
                      <ul className="ad-places">
                        {g.rows.map((a) => (
                          <li key={a.id} className={a.archived ? "ad-place-gone" : ""}>
                            <div className="ad-place-body">
                              <div className="ad-place-top">
                                <b>{a.label || "Address"}</b>
                                {a.isDefault && <span className="ad-place-default">Ships here</span>}
                                {a.archived && <span className="ad-place-tag">Removed</span>}
                              </div>
                              <small>
                                {[a.name, a.line, a.city].filter(Boolean).join(" · ")}
                                {a.phone ? ` · ${a.phone}` : ""}
                              </small>
                              {/* The same nouns the backend prints in red. */}
                              {!!a.gaps?.length && (
                                <p className="ad-place-gaps">
                                  <Icon n="info" size={14} />
                                  Missing {a.gaps.join(", ")}
                                </p>
                              )}
                            </div>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        )}

        {!loading && !rows.length && !error && (
          <Empty icon="pin"
            title={tab === "all" ? "No addresses yet" : "Nothing here"}
            text={tab === "all"
              ? "An address appears once a customer saves one in the app."
              : "No address matches that. Try another tab, or clear the search."} />
        )}

        {rows.length < total && (
          <div className="ad-more">
            <button className="ad-btn" onClick={() => setLimit((l) => l + PAGE)}>
              Show more ({total - rows.length} left)
            </button>
          </div>
        )}
      </section>

      {viewing && <CustomerDrawer row={viewing} onClose={() => setViewing(null)} />}
    </div>
  );
}
