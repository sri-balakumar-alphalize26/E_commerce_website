"use client";
/* ==========================================================================
   369 Mart admin — Support

   The screen that was missing entirely. A shopper could already ask the bot
   for a person, and that really opened a `mart369.ticket` - but every support
   route is fenced to the shopper's own partner, so the ticket went into a
   queue nobody could see. Somebody typed "I need help" and waited.

   Its own file rather than more of AdminMore.jsx, which is already three
   sections long and is where two people keep editing the same lines.

   Two rules carried from the other live sections:

     - **The next step is the server's.** `row.next.label` and `row.next.action`
       come from the model, so the words on a button cannot drift from what
       pressing it does.
     - **A reply is never appended locally.** Answering a ticket is also what
       claims it and stamps it answered, so the screen re-reads rather than
       guessing what its state became.
   ========================================================================== */
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { useAction, useResource } from "@/lib/useFetch";
import { Avatar, Confirm, Drawer, Empty, Icon, Pill, Search, Select, Tabs } from "./AdminUI";
import { dateTime, since } from "./format";

const PAGE = 30;

/* The tabs, in the order a ticket really moves. `needs` is what the screen
   opens on: somebody is waiting and nobody has replied. */
const TABS = [
  ["needs", "Needs a reply"],
  ["new", "Waiting"],
  ["open", "Being handled"],
  ["waiting", "On the customer"],
  ["done", "Answered"],
  ["all", "All"],
];

/* Tones for the state chip. Keys are the model's own five. */
const STATE_TONE = {
  new: { label: "Waiting", tone: "amber" },
  open: { label: "Being handled", tone: "blue" },
  waiting: { label: "On the customer", tone: "violet" },
  done: { label: "Answered", tone: "green" },
  cancelled: { label: "Dropped", tone: "grey" },
};

/** How long somebody has been waiting, in words. The number is the server's -
 *  it works it out live, because the stored one on the model is frozen for
 *  exactly the tickets that matter. */
function waitedFor(mins) {
  if (!mins) return "just now";
  if (mins < 60) return `${mins} min`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours} h`;
  return `${Math.round(hours / 24)} d`;
}

/* ============================== conversation ============================= */
function TicketDrawer({ ref_, staff, onClose, onChanged, flash }) {
  const { data, loading, error, reload } = useResource(
    `/admin/support/${encodeURIComponent(ref_)}`, { deps: [ref_] });
  const act = useAction();
  const [text, setText] = useState("");
  const t = data?.ticket;

  /* Re-read after every write. Replying is also what claims the ticket and
     stamps it answered, and the panel must not have to work that out. */
  const run = async (fn, ok) => {
    const done = await act.run(async () => { await fn(); return true; });
    if (done === null) {
      flash?.(act.error?.message || "That did not work.", "bad");
      return false;
    }
    api.invalidate("/admin/support");
    await reload();
    onChanged?.();
    if (ok) flash?.(ok);
    return true;
  };

  const send = async () => {
    const said = text.trim();
    if (!said) return;
    const ok = await run(
      () => api(`/admin/support/${encodeURIComponent(ref_)}/reply`,
        { method: "POST", body: { text: said } }),
      "Reply sent");
    if (ok) setText("");
  };

  const move = (action, ok) =>
    run(() => api(`/admin/support/${encodeURIComponent(ref_)}`,
      { method: "PATCH", body: { state: action } }), ok);

  /* An empty choice clears it rather than being refused: taking a name off a
     ticket is how it goes back to the pile. */
  const assign = (userId) =>
    run(() => api(`/admin/support/${encodeURIComponent(ref_)}`,
      { method: "PATCH", body: { assignee: userId ? Number(userId) : null } }),
      userId ? "Handed over" : "Back in the pile");

  return (
    <Drawer wide onClose={onClose}
      title={`Ticket ${ref_}`}
      sub={t ? `${t.customer} · ${dateTime(t.openedAt)}` : "Loading…"}
      foot={(close) => (
        <>
          {/* Hidden rather than disabled once a ticket is closed: the model
              refuses it, so offering the button is a trap. */}
          {t?.canReply && (
            <button className="ad-btn" disabled={act.busy}
              onClick={() => move("wait", "Waiting on the customer")}>
              Waiting on them
            </button>
          )}
          {t?.next && (
            <button className="ad-btn ad-primary" disabled={act.busy}
              onClick={() => move(t.next.action, `${t.next.label} — done`)}>
              {t.next.label}<Icon n="right" size={15} />
            </button>
          )}
          {!t?.next && <button className="ad-btn ad-primary" onClick={close}>Close</button>}
        </>
      )}>

      {error && <Empty icon="info" title="We could not reach the shop"
        text={error.message} action="Try again" onAction={reload} />}
      {loading && !t && !error && <Empty icon="chat" title="Loading…" text="Fetching the conversation." />}

      {t && (
        <>
          <section className="ad-dsec">
            <h4>What they asked</h4>
            <p className="ad-ticket-subject">{t.subject}</p>
            <div className="ad-ticket-meta">
              <Pill s={t.state} map={STATE_TONE} />
              {t.order && <span><Icon n="box" size={14} />{t.order}</span>}
              <span><Icon n="clock" size={14} />waited {waitedFor(t.waited)}</span>
            </div>
            <div className="ad-ticket-assign">
              <Select value={t.assigneeId ? String(t.assigneeId) : ""} onChange={assign}
                label="Handled by"
                options={[["", "Nobody yet"], ...(staff || []).map((p) => [String(p.id), p.name])]} />
            </div>
          </section>

          <section className="ad-dsec">
            <h4>Conversation</h4>
            {!t.messages?.length && <p className="ad-hint">Nothing said yet.</p>}
            <ul className="ad-thread">
              {(t.messages || []).map((m, i) => (
                <li key={i} className={m.from === "me" ? "ad-them" : "ad-us"}>
                  <p>{m.text}</p>
                  <small>{m.from === "me" ? t.customer : "Us"} · {since(m.at)}</small>
                </li>
              ))}
            </ul>
          </section>

          {t.canReply && (
            <section className="ad-dsec">
              <h4>Reply</h4>
              <textarea className="ad-reply" rows={3} value={text} maxLength={500}
                placeholder="Type what the customer should read…"
                onChange={(e) => setText(e.target.value)} />
              <div className="ad-reply-act">
                <small>{500 - text.length} left</small>
                <button className="ad-btn ad-primary" disabled={act.busy || !text.trim()}
                  onClick={send}>Send reply</button>
              </div>
            </section>
          )}
        </>
      )}
    </Drawer>
  );
}

/* ================================ the queue ============================== */
export function SupportSection({ openRef, setOpenRef, flash }) {
  const [tab, setTab] = useState("needs");
  const [term, setTerm] = useState("");
  const [q, setQ] = useState("");
  const [mine, setMine] = useState("");
  const [assignee, setAssignee] = useState("");
  const [limit, setLimit] = useState(PAGE);
  const [drop, setDrop] = useState(null);

  useEffect(() => {
    const id = setTimeout(() => { setQ(term.trim()); setLimit(PAGE); }, 300);
    return () => clearTimeout(id);
  }, [term]);

  const path = useMemo(() => {
    const p = new URLSearchParams({ tab, limit: String(limit) });
    if (q) p.set("q", q);
    if (mine) p.set("mine", mine);
    else if (assignee) p.set("assignee", assignee);
    return "/admin/support?" + p.toString();
  }, [tab, q, mine, assignee, limit]);

  /* `keepLast` because this one polls. Without it a single failed tick sets
     `data` to null, the queue collapses to the error placeholder, and the next
     good tick mounts every row again - replaying every staggered entrance,
     which reads as the screen reloading itself. Reviews does not take it: it
     does not poll, so there is never a last good read to keep. */
  const { data, loading, error, reload } = useResource(path, { pollMs: 30000, keepLast: true });
  const act = useAction();

  const rows = data?.tickets || [];
  const counts = data?.counts || {};
  const staff = data?.staff || [];
  const total = data?.total || 0;

  const refresh = async () => { api.invalidate("/admin/support"); await reload(); };

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

  const advance = (t) =>
    run(() => api(`/admin/support/${encodeURIComponent(t.ref)}`,
      { method: "PATCH", body: { state: t.next.action } }), `${t.ref} — ${t.next.label}`);

  const take = (t) =>
    run(() => api(`/admin/support/${encodeURIComponent(t.ref)}`,
      { method: "PATCH", body: { state: "take" } }), `${t.ref} is yours`);

  return (
    <div className="ad-stack">
      <section className="ad-mini-stats">
        <span className="ad-warn"><small>Needs a reply</small><b>{counts.needs ?? 0}</b></span>
        <span className="ad-bad"><small>Waiting over 30 min</small><b>{data?.late ?? 0}</b></span>
        <span><small>Longest wait</small><b>{waitedFor(data?.longest ?? 0)}</b></span>
        <span><small>Answered today</small><b>{data?.answeredToday ?? 0}</b></span>
      </section>

      <section className="ad-card">
        <div className="ad-toolbar">
          <Tabs value={tab} onChange={(v) => { setTab(v); setLimit(PAGE); }}
            tabs={TABS.map(([k, label]) => [k, label, counts[k] ?? null])} />
          <div className="ad-toolbar-right">
            <Search value={term} onChange={setTerm} placeholder="Ticket, customer or question" />
            <Select value={mine} onChange={(v) => { setMine(v); setLimit(PAGE); }} label="Whose"
              options={[["", "Anyone's"], ["1", "Mine only"]]} />
            <Select value={assignee} onChange={(v) => { setAssignee(v); setLimit(PAGE); }} label="Handled by"
              options={[["", "Anybody"], ...staff.map((s) => [String(s.id), s.name])]} />
          </div>
        </div>

        {error && <Empty icon="info" title="We could not reach the shop"
          text={error.message} action="Try again" onAction={reload} />}
        {loading && !rows.length && !error && (
          <Empty icon="chat" title="Loading…" text="Fetching the queue." />
        )}

        {!error && !!rows.length && (
          <ul className="ad-tickets">
            {rows.map((t, i) => (
              <li key={t.ref} style={{ "--i": i }}
                className={t.late ? "ad-ticket-late" : ""}
                onClick={(e) => {
                  if (e.target.closest("button,select,a,input")) return;
                  setOpenRef(t.ref);
                }}>
                <Avatar name={t.customer} size={38}
                  tone={t.late ? "ad-a-red" : t.answeredAt ? "ad-a-green" : "ad-a-orange"} />
                <div className="ad-ticket-body">
                  <div className="ad-ticket-top">
                    <b>{t.subject || "No subject"}</b>
                    <Pill s={t.state} map={STATE_TONE} />
                    {t.order && <span className="ad-ticket-order">{t.order}</span>}
                  </div>
                  <small>
                    {t.ref} · {t.customer} · waited {waitedFor(t.waited)}
                    {t.assignee ? ` · ${t.assignee}` : " · nobody yet"}
                    {t.replies ? ` · ${t.replies} message${t.replies === 1 ? "" : "s"}` : ""}
                  </small>
                </div>
                <div className="ad-ticket-act">
                  {t.next && (
                    <button className="ad-btn ad-sm ad-primary" disabled={act.busy}
                      onClick={() => advance(t)}>{t.next.label}</button>
                  )}
                  {t.state !== "cancelled" && t.state !== "done" && (
                    <button className="ad-btn ad-sm" disabled={act.busy}
                      onClick={() => setDrop(t)}>Drop</button>
                  )}
                  {!t.assignee && t.state !== "done" && (
                    <button className="ad-btn ad-sm" disabled={act.busy}
                      onClick={() => take(t)}>Take it</button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}

        {!loading && !rows.length && !error && (
          <Empty icon="chat"
            title={tab === "needs" ? "Nobody is waiting" : "Nothing here"}
            text={tab === "needs"
              ? "Every ticket has had a reply. That is the queue empty, not broken."
              : "No ticket matches that. Try another tab, or clear the search."} />
        )}

        {rows.length < total && (
          <div className="ad-more">
            <button className="ad-btn" onClick={() => setLimit((l) => l + PAGE)}>
              Show more ({total - rows.length} left)
            </button>
          </div>
        )}
      </section>

      {openRef && (
        <TicketDrawer ref_={openRef} staff={staff} flash={flash}
          onClose={() => setOpenRef(null)} onChanged={refresh} />
      )}

      {drop && (
        <Confirm danger title="Drop this ticket?" confirmLabel="Drop it"
          text={`${drop.ref} from ${drop.customer} will be closed without an answer. They are not told.`}
          onCancel={() => setDrop(null)}
          onConfirm={() => {
            const t = drop;
            setDrop(null);
            run(() => api(`/admin/support/${encodeURIComponent(t.ref)}`,
              { method: "PATCH", body: { state: "drop" } }), `${t.ref} dropped`);
          }} />
      )}
    </div>
  );
}
