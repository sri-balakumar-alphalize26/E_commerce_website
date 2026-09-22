"use client";
/* ==========================================================================
   369 Mart admin — Rewards

   Scratch cards, which are money: a delivered order mints one, and scratching
   it credits the 369 Wallet out of the shop's pocket.

   **This screen is read-only, on purpose.** It answers "what have we paid out,
   and what is still waiting to be opened". There is no button here that mints,
   edits or voids a card, and there is no route behind one either - a screen
   that can create a prize is a screen that can quietly pay somebody. So unlike
   every other live section this file has no `run()` helper and no `Confirm`:
   there is nothing to write.

   Money is formatted through lib/money.js with the currency the server sent,
   never by gluing a symbol onto a number. A card keeps the currency it was
   minted in, so a prize already promised is not revalued by a later change of
   company currency.
   ========================================================================== */
import { useEffect, useMemo, useState } from "react";
import { useResource } from "@/lib/useFetch";
import { Avatar, Empty, Pill, Search, Tabs } from "./AdminUI";
import { dateTime, since } from "./format";
import { money } from "@/lib/money";

const PAGE = 30;

/* The tabs, in the order somebody reads them: what is still owed first. */
const TABS = [
  ["unscratched", "Waiting to be opened"],
  ["cash", "Cash won"],
  ["coupon", "Coupon won"],
  ["nothing", "Won nothing"],
  ["all", "All"],
];

/* What the card turned out to be worth. `none` is deliberately grey rather
   than red: winning nothing is the common outcome, not a fault. */
const REWARD_TONE = {
  cash: { label: "Cash", tone: "green" },
  coupon: { label: "Coupon", tone: "violet" },
  none: { label: "No prize", tone: "grey" },
};

export function RewardsSection({ flash }) {
  const [tab, setTab] = useState("unscratched");
  const [term, setTerm] = useState("");
  const [q, setQ] = useState("");
  const [limit, setLimit] = useState(PAGE);

  useEffect(() => {
    const id = setTimeout(() => { setQ(term.trim()); setLimit(PAGE); }, 300);
    return () => clearTimeout(id);
  }, [term]);

  const path = useMemo(() => {
    const p = new URLSearchParams({ tab, limit: String(limit) });
    if (q) p.set("q", q);
    return "/admin/rewards?" + p.toString();
  }, [tab, q, limit]);

  /* `keepLast` because this one polls: without it a single failed tick empties
     the list and the next good tick replays every row's entrance. */
  const { data, loading, error, reload } = useResource(path, { pollMs: 60000, keepLast: true });

  const rows = data?.cards || [];
  const counts = data?.counts || {};
  const currency = data?.currency;
  const total = data?.total || 0;

  return (
    <div className="ad-stack">
      <section className="ad-mini-stats">
        <span><small>Cards minted</small><b>{counts.all ?? 0}</b></span>
        <span className="ad-warn"><small>Waiting to be opened</small><b>{counts.unscratched ?? 0}</b></span>
        <span><small>Paid out</small><b>{money(data?.paidAmount ?? 0, currency)}</b></span>
        <span><small>Won nothing</small><b>{counts.nothing ?? 0}</b></span>
      </section>

      <section className="ad-card">
        <div className="ad-toolbar">
          <Tabs value={tab} onChange={(v) => { setTab(v); setLimit(PAGE); }}
            tabs={TABS.map(([k, label]) => [k, label, counts[k] ?? null])} />
          <div className="ad-toolbar-right">
            <Search value={term} onChange={setTerm} placeholder="Customer or order" />
          </div>
        </div>

        {error && <Empty icon="info" title="We could not reach the shop"
          text={error.message} action="Try again" onAction={reload} />}
        {loading && !rows.length && !error && (
          <Empty icon="gift" title="Loading…" text="Fetching the cards." />
        )}

        {!error && !!rows.length && (
          <ul className="ad-prizes">
            {rows.map((c, i) => (
              <li key={c.id} style={{ "--i": i }}>
                <Avatar name={c.customer} size={38}
                  tone={c.reward === "cash" ? "ad-a-green" : c.reward === "coupon" ? "ad-a-blue" : "ad-a-navy"} />
                <div className="ad-prize-body">
                  <div className="ad-prize-top">
                    <b>{c.reward === "cash"
                      ? money(c.amount, currency)
                      : c.reward === "coupon" ? (c.coupon || "A coupon") : "No prize"}</b>
                    <Pill s={c.reward} map={REWARD_TONE} />
                    {!c.scratched && <span className="ad-prize-shut">Not opened yet</span>}
                  </div>
                  <small>
                    {c.customer} · {c.origin}
                    {c.scratched
                      ? ` · opened ${since(c.scratchedAt)}`
                      : ` · minted ${dateTime(c.mintedAt)}`}
                  </small>
                </div>
              </li>
            ))}
          </ul>
        )}

        {!loading && !rows.length && !error && (
          <Empty icon="gift"
            title={tab === "unscratched" ? "Every card has been opened" : "Nothing here"}
            text={tab === "unscratched"
              ? "Nobody is sitting on an unopened prize. That is the list empty, not broken."
              : "No card matches that. Try another tab, or clear the search."} />
        )}

        {rows.length < total && (
          <div className="ad-more">
            <button className="ad-btn" onClick={() => setLimit((l) => l + PAGE)}>
              Show more ({total - rows.length} left)
            </button>
          </div>
        )}
      </section>
    </div>
  );
}
