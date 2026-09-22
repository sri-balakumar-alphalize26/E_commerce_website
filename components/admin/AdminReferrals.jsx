"use client";
/* ==========================================================================
   369 Mart admin — Referrals

   Deliberately read-only bar one number.

   An invite moves by itself: `invited` when a customer sends it from the app,
   `joined` when somebody signs up carrying their code, `ordered` when that
   person's first order is paid for and the reward lands in the inviter's
   wallet. Every one of those is a claim about something that really happened,
   so none of them is a button here — a staff member who could mark an invite
   "Rewarded" by hand would be paying for an order nobody placed.

   What staff can change is what the next reward is worth, because that is a
   marketing decision rather than a fact. Rewards already paid keep what they
   were worth: the amount is copied onto the row when it is paid.
   ========================================================================== */
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { money } from "@/lib/money";
import { useAction, useResource } from "@/lib/useFetch";
import { Empty, Icon, Pill, Search, Tabs } from "./AdminUI";
import { dateTime, since } from "./format";

const STATES = {
  invited: { label: "Waiting", tone: "grey" },
  joined: { label: "Joined", tone: "blue" },
  ordered: { label: "Rewarded", tone: "green" },
};

export function ReferralsSection({ flash }) {
  const [tab, setTab] = useState("all");
  /* What is typed and what has been asked for, kept apart the way Orders and
     Reviews keep them: without the gap every keystroke is a request, and on a
     slow connection the answers come back out of order. */
  const [term, setTerm] = useState("");
  const [q, setQ] = useState("");
  const [reward, setReward] = useState("");
  const [editingReward, setEditingReward] = useState(false);

  useEffect(() => {
    const id = setTimeout(() => setQ(term.trim()), 300);
    return () => clearTimeout(id);
  }, [term]);

  const path = useMemo(() => {
    const p = new URLSearchParams();
    if (tab !== "all") p.set("state", tab);
    if (q) p.set("q", q);
    const qs = p.toString();
    return "/admin/referrals" + (qs ? `?${qs}` : "");
  }, [tab, q]);

  const { data, loading, error, reload } = useResource(path);
  const act = useAction();

  const rows = data?.rows || [];
  const counts = data?.counts || {};
  const tiles = data?.tiles || {};
  const currency = tiles.currency;

  /* Read-after-write, as everywhere else in this console: the tiles and the
     reward are both the server's answer, and a number patched locally would
     disagree with what the next customer is actually paid. */
  const run = (fn, ok) =>
    act.run(async () => {
      await fn();
      api.invalidate("/admin/referrals");
      await reload();
      if (ok) flash?.(ok);
      return true;
    }).then((r) => {
      if (r === null) flash?.(act.error?.message || "That did not work.", "bad");
      return r;
    });

  async function saveReward() {
    const amount = Number(reward);
    if (!Number.isFinite(amount) || amount < 0) {
      flash?.("Enter the reward as a number.", "bad");
      return;
    }
    const done = await run(
      () => api("/admin/referrals/reward", { method: "PATCH", body: { reward: amount } }),
      `A referral now pays ${money(amount, currency)}`
    );
    if (done) setEditingReward(false);
  }

  return (
    <div className="ad-stack">
      {/* The five the Odoo strip draws, with the same words and the same
          sub-lines, so a manager who has both open is never told two
          different things. Every figure was already in the payload; the
          console simply was not drawing most of it. Money goes through
          `money()` rather than the server's pre-formatted `paid`/`reward`
          strings - that is what the raw amounts are there for. */}
      <section className="ad-mini-stats ad-mini-5">
        <span>
          <small>Waiting</small><b>{tiles.invited ?? 0}</b>
          <i>{tiles.total ?? 0} invites in all</i>
        </span>
        <span>
          <small>Signed up</small><b>{tiles.joined ?? 0}</b>
          <i>not ordered yet</i>
        </span>
        <span>
          <small>Ordered</small><b>{tiles.ordered ?? 0}</b>
          <span className="ad-meter" aria-hidden="true">
            <i style={{ width: `${Math.min(100, tiles.conversion ?? 0)}%` }} />
          </span>
        </span>
        <span>
          <small>Paid out</small><b>{money(tiles.paid_amount ?? 0, currency)}</b>
          <i>{money(tiles.reward_amount ?? 0, currency)} each</i>
        </span>
        <span>
          <small>Invites that buy</small><b>{tiles.conversion ?? 0}%</b>
          <i>of everyone invited</i>
        </span>
      </section>

      <section className="ad-card ad-ref-setting">
        <div>
          <b>One referral pays {money(tiles.reward_amount ?? 0, currency)}</b>
          <small>
            Changing this only changes what is paid next — rewards already
            paid keep what they were worth.
          </small>
        </div>
        {editingReward ? (
          <div className="ad-ref-edit">
            <input type="number" min="0" step="1" autoFocus className="ad-ref-input"
              value={reward} onChange={(e) => setReward(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") saveReward();
                if (e.key === "Escape") setEditingReward(false);
              }} />
            <button className="ad-btn ad-primary" disabled={act.busy} onClick={saveReward}>Save</button>
            <button className="ad-btn" disabled={act.busy} onClick={() => setEditingReward(false)}>Cancel</button>
          </div>
        ) : (
          <button className="ad-btn" onClick={() => {
            setReward(String(tiles.reward_amount ?? 0));
            setEditingReward(true);
          }}><Icon n="gear" size={16} />Change reward</button>
        )}
      </section>

      <section className="ad-card">
        <div className="ad-toolbar">
          <Tabs value={tab} onChange={setTab} tabs={[
            ["all", "All", counts.all ?? 0],
            ["invited", "Waiting", counts.invited ?? 0],
            ["joined", "Joined", counts.joined ?? 0],
            ["ordered", "Rewarded", counts.ordered ?? 0],
          ]} />
          <div className="ad-toolbar-right">
            <Search value={term} onChange={setTerm} placeholder="Friend, contact or who invited" />
          </div>
        </div>

        {error && (
          <Empty icon="info" title="We could not reach the shop" text={error.message}
            action="Try again" onAction={reload} />
        )}
        {loading && !rows.length && !error && (
          <Empty icon="users" title="Loading…" text="Fetching invites." />
        )}
        {!error && !loading && !rows.length && (
          <Empty icon="users" title="No invites here"
            text={q || tab !== "all"
              ? "Nothing matches that. Try another tab, or clear the search."
              : "Invites appear here as customers send them from the app."} />
        )}

        {!error && !!rows.length && (
          <div className="ad-table-wrap">
            <table className="ad-table">
              <thead>
                <tr>
                  <th>Friend</th><th>Invited by</th><th>Status</th>
                  <th>First order</th><th>Reward</th><th>Sent</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id}>
                    <td>
                      <b>{r.friend || "A friend"}</b>
                      {r.contact ? <small className="ad-sub">{r.contact}</small> : null}
                      {r.joinedAs && r.joinedAs !== r.friend
                        ? <small className="ad-sub">signed up as {r.joinedAs}</small>
                        : null}
                    </td>
                    <td>
                      {r.invitedBy}
                      {r.inviterCode ? <small className="ad-sub">{r.inviterCode}</small> : null}
                    </td>
                    <td><Pill s={r.state} map={STATES} /></td>
                    <td>{r.order || <span className="ad-muted">—</span>}</td>
                    <td>{r.reward ? money(r.reward, currency) : <span className="ad-muted">—</span>}</td>
                    <td title={r.at ? dateTime(r.at) : ""}>{r.at ? since(r.at) : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
