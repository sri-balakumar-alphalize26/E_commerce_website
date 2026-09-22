"use client";
/* ==========================================================================
   369 Mart admin — Notifications

   A notice is a line that turns up in every customer's notification list. So
   this screen writes, but narrowly: the words, when it runs, and taking it
   down. There is no delete — somebody has already read it, and removing the
   record does not untell them. Retiring one stops it appearing to anybody new.

   **A notice has no status field, and should not.** Live, scheduled and
   expired all fall out of the two dates and whether it is switched on, and the
   server works that out. The screen prints `state`; it never decides it, or
   the two would disagree the moment a clock ticked past a date.
   ========================================================================== */
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { useAction, useResource } from "@/lib/useFetch";
import { Confirm, Drawer, Empty, Icon, Pill, Search, Select, Tabs } from "./AdminUI";
import { dateTime } from "./format";

const PAGE = 30;

const TABS = [
  ["live", "Live now"],
  ["scheduled", "Scheduled"],
  ["expired", "Finished"],
  ["off", "Taken down"],
  ["all", "All"],
];

/* What the server calls each state, in the console's own colours. */
const STATE_TONE = {
  live: { label: "Live", tone: "green" },
  scheduled: { label: "Scheduled", tone: "blue" },
  expired: { label: "Finished", tone: "grey" },
  off: { label: "Taken down", tone: "amber" },
};

const BLANK = { name: "", text: "", kind: "offer", publish_at: "", until: "", go_view: "", go_param: "" };

/** Odoo speaks "YYYY-MM-DD HH:MM:SS"; a datetime-local input speaks
 *  "YYYY-MM-DDTHH:MM". Translate at the edge rather than in the payload. */
function toInput(ms) {
  if (!ms) return "";
  const d = new Date(ms);
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
function toOdoo(value) {
  return value ? value.replace("T", " ") + ":00" : false;
}

/* ================================ the form =============================== */
function NoticeDrawer({ notice, kinds, onClose, onSaved, flash }) {
  const act = useAction();
  const [form, setForm] = useState(() => (notice
    ? {
      name: notice.title, text: notice.text, kind: notice.kind,
      publish_at: toInput(notice.from), until: toInput(notice.until),
      go_view: notice.goView, go_param: notice.goParam,
    }
    : { ...BLANK }));
  const [error, setError] = useState("");
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const save = async () => {
    setError("");
    const body = {
      ...form,
      publish_at: toOdoo(form.publish_at),
      until: toOdoo(form.until),
    };
    const done = await act.run(async () => {
      await api(notice ? `/admin/notices/${notice.id}` : "/admin/notices",
        { method: notice ? "PATCH" : "POST", body });
      return true;
    });
    if (done === null) {
      /* The drawer stays open with the message in it: closing it and flashing
         would throw away everything just typed. */
      setError(act.error?.message || "That could not be saved.");
      return;
    }
    api.invalidate("/admin/notices");
    onSaved(notice ? "Notification updated" : "Notification written");
  };

  return (
    <Drawer wide onClose={onClose}
      title={notice ? "Edit notification" : "New notification"}
      sub={notice ? `Written ${dateTime(notice.from)}` : "It appears in every customer's list"}
      foot={(close) => (
        <>
          <button className="ad-btn" onClick={close}>Cancel</button>
          <button className="ad-btn ad-primary" disabled={act.busy} onClick={save}>
            {notice ? "Save" : "Write it"}<Icon n="right" size={15} />
          </button>
        </>
      )}>

      {error && <p className="ad-form-error" role="alert">{error}</p>}

      <section className="ad-dsec">
        <h4>What it says</h4>
        <label className="ad-field ad-span2">
          <span>Title</span>
          <span className="ad-field-in">
            <input value={form.name} onChange={(e) => set("name", e.target.value)}
              placeholder="Weekend grocery sale is live" />
          </span>
        </label>
        <label className="ad-field ad-span2">
          <span>Words</span>
          <textarea className="ad-reply" rows={3} value={form.text}
            onChange={(e) => set("text", e.target.value)}
            placeholder="Up to 40% off on fresh picks. Ends Sunday midnight." />
        </label>
        <div className="ad-field">
          <span>Kind</span>
          <Select value={form.kind} onChange={(v) => set("kind", v)} label="Kind"
            options={(kinds || []).map((k) => [k.key, k.label])} />
        </div>
      </section>

      <section className="ad-dsec">
        <h4>When it runs</h4>
        <p className="ad-hint">
          Leave the end empty and it runs until somebody takes it down.
        </p>
        <label className="ad-field">
          <span>Show from</span>
          <span className="ad-field-in">
            <input type="datetime-local" value={form.publish_at}
              onChange={(e) => set("publish_at", e.target.value)} />
          </span>
        </label>
        <label className="ad-field">
          <span>Show until</span>
          <span className="ad-field-in">
            <input type="datetime-local" value={form.until}
              onChange={(e) => set("until", e.target.value)} />
          </span>
        </label>
      </section>

      <section className="ad-dsec">
        <h4>Where tapping it goes</h4>
        <label className="ad-field">
          <span>Screen</span>
          <span className="ad-field-in">
            <input value={form.go_view} onChange={(e) => set("go_view", e.target.value)}
              placeholder="offers" />
          </span>
        </label>
        <label className="ad-field">
          <span>With</span>
          <span className="ad-field-in">
            <input value={form.go_param} onChange={(e) => set("go_param", e.target.value)}
              placeholder="wallet" />
          </span>
        </label>
      </section>
    </Drawer>
  );
}

/* ================================ the list =============================== */
export function NotificationsSection({ flash }) {
  const [tab, setTab] = useState("live");
  const [term, setTerm] = useState("");
  const [q, setQ] = useState("");
  const [limit, setLimit] = useState(PAGE);
  const [editing, setEditing] = useState(null); // a notice, or {} for a new one
  const [drop, setDrop] = useState(null);

  useEffect(() => {
    const id = setTimeout(() => { setQ(term.trim()); setLimit(PAGE); }, 300);
    return () => clearTimeout(id);
  }, [term]);

  const path = useMemo(() => {
    const p = new URLSearchParams({ tab, limit: String(limit) });
    if (q) p.set("q", q);
    return "/admin/notices?" + p.toString();
  }, [tab, q, limit]);

  const { data, loading, error, reload } = useResource(path, { pollMs: 60000, keepLast: true });
  const act = useAction();

  const rows = data?.notices || [];
  const counts = data?.counts || {};
  const kinds = data?.kinds || [];
  const total = data?.total || 0;

  /* Read-after-write. Whether a notice is live or scheduled depends on the
     clock, so the screen re-reads rather than guessing what it became. */
  const run = (fn, ok) =>
    act.run(async () => {
      await fn();
      api.invalidate("/admin/notices");
      await reload();
      if (ok) flash?.(ok);
      return true;
    }).then((r) => {
      if (r === null) flash?.(act.error?.message || "That did not work.", "bad");
      return r;
    });

  const retire = (n, retired) =>
    run(() => api(`/admin/notices/${n.id}`, { method: "PATCH", body: { retired } }),
      retired ? "Taken down" : "Back up");

  return (
    <div className="ad-stack">
      <section className="ad-mini-stats">
        <span><small>Live now</small><b>{counts.live ?? 0}</b></span>
        <span><small>Scheduled</small><b>{counts.scheduled ?? 0}</b></span>
        <span><small>Finished</small><b>{counts.expired ?? 0}</b></span>
        <span className="ad-warn"><small>Taken down</small><b>{counts.off ?? 0}</b></span>
      </section>

      <section className="ad-card">
        <div className="ad-toolbar">
          <Tabs value={tab} onChange={(v) => { setTab(v); setLimit(PAGE); }}
            tabs={TABS.map(([k, label]) => [k, label, counts[k] ?? null])} />
          <div className="ad-toolbar-right">
            <Search value={term} onChange={setTerm} placeholder="Title or words" />
            <button className="ad-btn ad-primary" onClick={() => setEditing({})}>
              <Icon n="plus" size={16} />New notification
            </button>
          </div>
        </div>

        {error && <Empty icon="info" title="We could not reach the shop"
          text={error.message} action="Try again" onAction={reload} />}
        {loading && !rows.length && !error && (
          <Empty icon="bell" title="Loading…" text="Fetching notifications." />
        )}

        {!error && !!rows.length && (
          <ul className="ad-notices">
            {rows.map((n, i) => (
              <li key={n.id} style={{ "--i": i }} className={n.state === "off" ? "ad-notice-off" : ""}>
                <div className="ad-notice-body">
                  <div className="ad-notice-top">
                    <b>{n.title}</b>
                    <Pill s={n.state} map={STATE_TONE} />
                    <span className="ad-notice-kind">{n.kindLabel}</span>
                  </div>
                  <p>{n.text}</p>
                  <small>
                    {n.state === "scheduled" ? "Starts " : "From "}{dateTime(n.from)}
                    {n.until ? ` · until ${dateTime(n.until)}` : " · no end date"}
                    {n.goView ? ` · opens ${[n.goView, n.goParam].filter(Boolean).join("/")}` : ""}
                  </small>
                </div>
                <div className="ad-notice-act">
                  <button className="ad-btn ad-sm" disabled={act.busy}
                    onClick={() => setEditing(n)}>Edit</button>
                  {n.state === "off"
                    ? <button className="ad-btn ad-sm" disabled={act.busy}
                      onClick={() => retire(n, false)}>Put back</button>
                    : <button className="ad-btn ad-sm" disabled={act.busy}
                      onClick={() => setDrop(n)}>Take down</button>}
                </div>
              </li>
            ))}
          </ul>
        )}

        {!loading && !rows.length && !error && (
          <Empty icon="bell"
            title={tab === "live" ? "Nothing is running" : "Nothing here"}
            text={tab === "live"
              ? "No notification is showing to customers right now."
              : "None match that. Try another tab, or clear the search."} />
        )}

        {rows.length < total && (
          <div className="ad-more">
            <button className="ad-btn" onClick={() => setLimit((l) => l + PAGE)}>
              Show more ({total - rows.length} left)
            </button>
          </div>
        )}
      </section>

      {editing && (
        <NoticeDrawer notice={editing.id ? editing : null} kinds={kinds} flash={flash}
          onClose={() => setEditing(null)}
          onSaved={async (msg) => { setEditing(null); await reload(); flash?.(msg); }} />
      )}

      {drop && (
        <Confirm danger title="Take this down?" confirmLabel="Take it down"
          text={`“${drop.title}” stops appearing to anybody new. Customers who have already seen it keep it in their list — taking it down does not untell them.`}
          onCancel={() => setDrop(null)}
          onConfirm={() => { const n = drop; setDrop(null); retire(n, true); }} />
      )}
    </div>
  );
}
