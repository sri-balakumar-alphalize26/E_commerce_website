"use client";
/* ==========================================================================
   369 Mart admin — Wallets

   Money customers have already paid us and have not spent yet. The total is a
   liability, not takings: every rupee of it will be spent or asked for back.

   **Read-only, deliberately.** The only thing that moves a balance is a
   top-up, an order, a refund or a reward — each a thing that actually
   happened, each leaving a movement the customer can see in their own app. A
   button here that credited a wallet would be money paid out with no approval,
   no cap and no second pair of eyes.

   The one alarm is **out of step**: a wallet whose balance does not equal its
   own movements. That is a bug, not something a customer did, and nothing here
   offers to "recalculate" it — writing the balance to match the ledger would
   destroy the evidence of whatever went wrong.
   ========================================================================== */
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { money } from "@/lib/money";
import { useResource } from "@/lib/useFetch";
import { Drawer, Empty, Icon, Pill, Search, Tabs } from "./AdminUI";
import { dateTime, since } from "./format";

/* The four kinds of movement, in the customer's own words — these are the
   same rows they see in the app, so they must read the same way. */
const KINDS = {
  add: { label: "Added", tone: "green" },
  spend: { label: "Spent", tone: "grey" },
  refund: { label: "Refunded", tone: "blue" },
  reward: { label: "Reward", tone: "violet" },
};
const OUT = new Set(["spend"]);

export function WalletsSection() {
  const [tab, setTab] = useState("all");
  const [term, setTerm] = useState("");
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(null);

  useEffect(() => {
    const id = setTimeout(() => setQ(term.trim()), 300);
    return () => clearTimeout(id);
  }, [term]);

  const path = useMemo(() => {
    const p = new URLSearchParams();
    if (tab !== "all") p.set("tab", tab);
    if (q) p.set("q", q);
    const qs = p.toString();
    return "/admin/wallets" + (qs ? `?${qs}` : "");
  }, [tab, q]);

  const { data, loading, error, reload } = useResource(path);

  const rows = data?.rows || [];
  const counts = data?.counts || {};
  const tiles = data?.tiles || {};
  const currency = tiles.currency;

  return (
    <div className="ad-stack">
      <section className="ad-mini-stats ad-pay-stats">
        <span><small>Wallets</small><b>{tiles.wallets ?? 0}</b><i>Show these</i></span>
        <span>
          <small>Money we hold</small>
          <b>{money(tiles.held_amount ?? 0, currency)}</b>
          <i>Already paid for, and still owed</i>
        </span>
        <span>
          <small>Largest balance</small>
          <b>{money(tiles.biggest_amount ?? 0, currency)}</b>
          <i>{tiles.biggest_who || " "}</i>
        </span>
        <span className={tiles.broken ? "ad-bad" : ""}>
          <small>Out of step</small>
          <b>{tiles.broken ?? 0}</b>
          <i>{tiles.broken ? "A bug, not a customer action" : "Every balance matches its history"}</i>
        </span>
      </section>

      {/* Only when there is something wrong. A banner that is always there is
          a banner nobody reads. */}
      {!!tiles.broken && (
        <p className="ad-hint ad-gap-note">
          <Icon n="info" size={14} />
          <span>
            <b>{tiles.broken}</b> wallet{tiles.broken === 1 ? "" : "s"}{" "}
            disagree{tiles.broken === 1 ? "s" : ""} with{" "}
            {tiles.broken === 1 ? "its" : "their"} own history. That is a bug,
            not something a customer did, and nothing on this screen can fix it —
            the balance and the movements are the evidence.
          </span>
        </p>
      )}

      <p className="ad-hint ad-readonly">
        <Icon n="info" size={14} />
        <span>
          Nothing here can be changed. A balance only moves through a top-up, an
          order, a refund or a reward — each one leaves a movement the customer
          can see in their own app.
        </span>
      </p>

      <section className="ad-card">
        <div className="ad-toolbar">
          <Tabs value={tab} onChange={setTab} tabs={[
            ["all", "All", counts.all ?? 0],
            ["money", "With money", counts.money ?? 0],
            ["empty", "Empty", counts.empty ?? 0],
            ["broken", "Out of step", counts.broken ?? 0],
          ]} />
          <div className="ad-toolbar-right">
            <Search value={term} onChange={setTerm} placeholder="A customer, an email or a phone" />
          </div>
        </div>

        {error && (
          <Empty icon="info" title="We could not reach the shop" text={error.message}
            action="Try again" onAction={reload} />
        )}
        {loading && !rows.length && !error && (
          <Empty icon="wallet" title="Loading…" text="Fetching wallets." />
        )}
        {!error && !loading && !rows.length && (
          <Empty icon="wallet"
            title={tab === "broken" ? "Every balance matches its own history" : "No wallet here"}
            text={tab === "broken"
              ? "That is the good version of this tab being empty."
              : q || tab !== "all"
                ? "Nothing matches that. Try another tab, or clear the search."
                : "A wallet is made for a customer the first time they top up or are paid a reward."} />
        )}

        {!error && !!rows.length && (
          <ul className="ad-wallets">
            {rows.map((r, i) => (
              <li key={r.id} className={r.consistent ? "" : "ad-wallet-bad"} style={{ "--i": i }}>
                <div className="ad-wallet-body">
                  <div className="ad-wallet-top">
                    {/* A wallet with nobody attached is odd enough to say
                        so: "A customer" would read like a real person. */}
                    {r.customer
                      ? <b>{r.customer}</b>
                      : <b className="ad-wallet-nobody">No customer</b>}
                    {/* A consistent wallet says nothing here. A tick on every
                        row trains people to ignore the one red one. */}
                    {!r.consistent && (
                      <span className="ad-pill ad-t-red">
                        <i />Balance {money(r.balance, r.currency || currency)}, history{" "}
                        {money(r.ledger, r.currency || currency)}
                      </span>
                    )}
                  </div>
                  <small>
                    {r.moves ? (
                      <>
                        {r.lastKind ? `${KINDS[r.lastKind]?.label || r.lastKind} · ` : ""}
                        {r.lastTitle}
                        {r.lastAt ? <> {" · "}<span title={dateTime(r.lastAt)}>{since(r.lastAt)}</span></> : null}
                        {` · ${r.moves} movement${r.moves === 1 ? "" : "s"}`}
                      </>
                    ) : "no movements yet"}
                    {r.email ? ` · ${r.email}` : ""}
                  </small>
                </div>
                <div className="ad-pay-worth">
                  <b>{money(r.balance, r.currency || currency)}</b>
                  <small>held</small>
                </div>
                <div className="ad-wallet-act">
                  <button className="ad-btn ad-sm" onClick={() => setOpen(r)}>Movements</button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      {open && <LedgerDrawer card={open} currency={currency} onClose={() => setOpen(null)} />}
    </div>
  );
}

/* One wallet's movements. The rows are the same six fields the customer sees
   in their own app — staff reading a different story about the same money is
   its own kind of lie. */
function LedgerDrawer({ card, currency, onClose }) {
  const [moves, setMoves] = useState([]);
  const [before, setBefore] = useState(null);
  const [head, setHead] = useState(card);
  const [busy, setBusy] = useState(true);
  const [err, setErr] = useState("");
  const [started, setStarted] = useState(false);

  async function more(cursor) {
    setBusy(true);
    try {
      const p = new URLSearchParams();
      if (cursor) p.set("before", cursor);
      const qs = p.toString();
      const page = await api(`/admin/wallets/${card.id}/ledger${qs ? `?${qs}` : ""}`);
      setHead(page.card || card);
      setMoves((m) => m.concat(page.moves || []));
      setBefore(page.before || null);
      setErr("");
    } catch (e) {
      setErr(e?.message || "We could not reach the shop.");
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    if (started) return;
    setStarted(true);
    more(null);
  }, [started]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <Drawer title={card.customer || "This wallet"} onClose={onClose}
      sub="These are the same movements the customer sees in their own app.">
      <div className="ad-ledger-head">
        <div><span>Balance</span><b>{money(head.balance, head.currency || currency)}</b></div>
        {/* Only drawn when it differs. Two numbers side by side that always
            agree is noise; two that disagree is the whole story. */}
        {!head.consistent && (
          <div className="ad-ledger-bad">
            <span>Its movements add up to</span>
            <b>{money(head.ledger, head.currency || currency)}</b>
          </div>
        )}
      </div>

      {err && <p className="ad-hint ad-form-error" role="alert"><Icon n="info" size={14} />{err}</p>}
      {busy && !moves.length && <p className="ad-hint">Loading movements…</p>}
      {!busy && !moves.length && !err && (
        <p className="ad-hint">Nothing has moved in this wallet yet.</p>
      )}

      {!!moves.length && (
        <ul className="ad-ledger">
          {moves.map((m) => (
            <li key={m.id}>
              <Pill s={m.kind} map={KINDS} />
              <span className="ad-ledger-txt">
                <b>{m.title}</b>
                {m.sub ? <small>{m.sub}</small> : null}
              </span>
              <span className="ad-ledger-when" title={m.at ? dateTime(m.at) : ""}>
                {m.at ? since(m.at) : ""}
              </span>
              <b className={"ad-ledger-amt " + (OUT.has(m.kind) ? "ad-out" : "ad-in")}>
                {OUT.has(m.kind) ? "−" : "+"}{money(m.amount, head.currency || currency)}
              </b>
            </li>
          ))}
        </ul>
      )}

      {before && (
        <p className="ad-ledger-more">
          <button className="ad-btn ad-sm" disabled={busy} onClick={() => more(before)}>
            Show older
          </button>
        </p>
      )}
    </Drawer>
  );
}
