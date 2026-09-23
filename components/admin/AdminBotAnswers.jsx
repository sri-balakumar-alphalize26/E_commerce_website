"use client";
/* ==========================================================================
   369 Mart admin — Bot answers

   What the shop says to a customer before a person sees them. The most
   editable of the staff screens, and the one where a mistake is quietest.

   **Order is meaning.** The bot tries these top to bottom and the first match
   wins, so a broad pattern moved above a narrow one silently swallows it —
   the narrow answer still exists, still looks fine here, and never fires
   again. That is why moving one is its own button rather than a number
   somebody edits, and why a new answer is added at the bottom.

   **A pattern is a regular expression.** One that will not compile used to
   save happily and then never match, for ever. The server refuses it now and
   names the field; this screen shows that message under the box it is about.

   **Switched off is not deleted.** Somebody wrote it for a reason.
   ========================================================================== */
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { useAction, useResource } from "@/lib/useFetch";
import { Confirm, Drawer, Empty, Icon, Pill, Search, Select, Tabs } from "./AdminUI";

const PAGE = 30;

const TABS = [
  ["on", "In use"],
  ["agent", "Hands over"],
  ["off", "Switched off"],
  ["all", "All"],
];

const STATE_TONE = {
  on: { label: "In use", tone: "green" },
  off: { label: "Switched off", tone: "grey" },
};

const BLANK = {
  title: "", pattern: "", kind: "static", reply: "", reply_alt: "",
  chips: "", action_label: "", action_view: "", action_param: "",
};

/* ================================ the form =============================== */
function AnswerDrawer({ answer, kinds, onClose, onSaved, flash }) {
  const act = useAction();
  const [form, setForm] = useState(() => (answer
    ? {
      title: answer.title, pattern: answer.pattern, kind: answer.kind,
      reply: answer.reply, reply_alt: answer.replyAlt,
      chips: (answer.chips || []).join(", "),
      action_label: answer.actionLabel, action_view: answer.actionView,
      action_param: answer.actionParam,
    }
    : { ...BLANK }));
  const [error, setError] = useState("");
  const [badField, setBadField] = useState("");
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  /* Only a fixed answer says the words typed below; every other kind runs
     code on the server and `reply` is a fallback. Worth saying, because it
     changes what editing the words actually does. */
  const saysTheWords = form.kind === "static";

  const save = async () => {
    setError("");
    setBadField("");
    const body = {
      ...form,
      chips: form.chips.split(",").map((c) => c.trim()).filter(Boolean),
    };
    const done = await act.run(async () => {
      await api(answer ? `/admin/answers/${answer.id}` : "/admin/answers",
        { method: answer ? "PATCH" : "POST", body });
      return true;
    });
    if (done === null) {
      setError(act.error?.message || "That could not be saved.");
      setBadField(act.error?.field || "");
      return;
    }
    api.invalidate("/admin/answers");
    onSaved(answer ? "Answer saved" : "Answer added at the bottom");
  };

  return (
    <Drawer wide onClose={onClose}
      title={answer ? "Edit answer" : "New answer"}
      sub={answer ? `Tried ${answer.sequence} in order` : "It goes last, so it takes no matches from the others"}
      foot={(close) => (
        <>
          <button className="ad-btn" onClick={close}>Cancel</button>
          <button className="ad-btn ad-primary" disabled={act.busy} onClick={save}>
            {answer ? "Save" : "Add it"}<Icon n="right" size={15} />
          </button>
        </>
      )}>

      {error && <p className="ad-form-error" role="alert">{error}</p>}

      <section className="ad-dsec">
        <h4>When it fires</h4>
        <label className="ad-field ad-span2">
          <span>What it covers</span>
          <span className="ad-field-in">
            <input value={form.title} onChange={(e) => set("title", e.target.value)}
              placeholder="Opening hours" />
          </span>
        </label>
        <label className={"ad-field ad-span2" + (badField === "pattern" ? " ad-field-bad" : "")}>
          <span>Matches</span>
          <span className="ad-field-in">
            <input value={form.pattern} onChange={(e) => set("pattern", e.target.value)}
              placeholder="\b(open|hours|timing)\b" />
          </span>
        </label>
        <p className="ad-hint">
          A pattern, not a phrase. The bot tries these in order and stops at
          the first one that matches.
        </p>
      </section>

      <section className="ad-dsec">
        <h4>What it answers</h4>
        <div className="ad-field">
          <span>Kind</span>
          <Select value={form.kind} onChange={(v) => set("kind", v)} label="Kind"
            options={(kinds || []).map((k) => [k.key, k.label])} />
        </div>
        <label className="ad-field ad-span2">
          <span>{saysTheWords ? "Says" : "Says if the shop has nothing to tell them"}</span>
          <textarea className="ad-reply" rows={3} value={form.reply}
            onChange={(e) => set("reply", e.target.value)}
            placeholder="We are open 7am to 11pm, every day." />
        </label>
        {!saysTheWords && (
          <p className="ad-hint">
            This kind works the answer out from the customer&apos;s own orders,
            wallet or coupons. The words above are only used when there is
            nothing to tell them.
          </p>
        )}
        <label className="ad-field ad-span2">
          <span>Suggestions under it</span>
          <span className="ad-field-in">
            <input value={form.chips} onChange={(e) => set("chips", e.target.value)}
              placeholder="Talk to an agent, See offers" />
          </span>
        </label>
      </section>

      <section className="ad-dsec">
        <h4>Button under the answer</h4>
        <label className="ad-field">
          <span>Button says</span>
          <span className="ad-field-in">
            <input value={form.action_label} onChange={(e) => set("action_label", e.target.value)}
              placeholder="Open 369 Wallet" />
          </span>
        </label>
        <label className="ad-field">
          <span>Opens</span>
          <span className="ad-field-in">
            <input value={form.action_view} onChange={(e) => set("action_view", e.target.value)}
              placeholder="account" />
          </span>
        </label>
        <label className="ad-field">
          <span>With</span>
          <span className="ad-field-in">
            <input value={form.action_param} onChange={(e) => set("action_param", e.target.value)}
              placeholder="wallet" />
          </span>
        </label>
      </section>
    </Drawer>
  );
}

/* ================================ the list =============================== */
export function BotAnswersSection({ flash }) {
  const [tab, setTab] = useState("on");
  const [term, setTerm] = useState("");
  const [q, setQ] = useState("");
  const [limit, setLimit] = useState(PAGE);
  const [editing, setEditing] = useState(null);
  const [drop, setDrop] = useState(null);

  useEffect(() => {
    const id = setTimeout(() => { setQ(term.trim()); setLimit(PAGE); }, 300);
    return () => clearTimeout(id);
  }, [term]);

  const path = useMemo(() => {
    const p = new URLSearchParams({ tab, limit: String(limit) });
    if (q) p.set("q", q);
    return "/admin/answers?" + p.toString();
  }, [tab, q, limit]);

  const { data, loading, error, reload } = useResource(path, { pollMs: 60000, keepLast: true });
  const act = useAction();

  const rows = data?.answers || [];
  const counts = data?.counts || {};
  const kinds = data?.kinds || [];
  const total = data?.total || 0;

  const run = (fn, ok) =>
    act.run(async () => {
      await fn();
      api.invalidate("/admin/answers");
      await reload();
      if (ok) flash?.(ok);
      return true;
    }).then((r) => {
      if (r === null) flash?.(act.error?.message || "That did not work.", "bad");
      return r;
    });

  const switchIt = (a, on) =>
    run(() => api(`/admin/answers/${a.id}`, { method: "PATCH", body: { active: on } }),
      on ? "Back in use" : "Switched off");

  /* Moving one changes which answer wins, so it is sent as the whole order
     rather than as a number on a row. Only meaningful while the list is
     unfiltered — otherwise the ids sent are a subset and everything else
     would be renumbered around them. */
  const canReorder = tab === "all" && !q;
  const move = (index, by) => {
    const next = [...rows];
    const target = index + by;
    if (target < 0 || target >= next.length) return;
    [next[index], next[target]] = [next[target], next[index]];
    run(() => api("/admin/answers/order", { method: "POST", body: { ids: next.map((a) => a.id) } }),
      "Order changed");
  };

  return (
    <div className="ad-stack">
      <section className="ad-mini-stats">
        <span><small>In use</small><b>{counts.on ?? 0}</b></span>
        <span><small>Hands over to a person</small><b>{counts.agent ?? 0}</b></span>
        <span><small>Switched off</small><b>{counts.off ?? 0}</b></span>
        <span className={data?.broken ? "ad-bad" : ""}>
          <small>Cannot match</small><b>{data?.broken ?? 0}</b>
        </span>
      </section>

      <section className="ad-card">
        <div className="ad-toolbar">
          <Tabs value={tab} onChange={(v) => { setTab(v); setLimit(PAGE); }}
            tabs={TABS.map(([k, label]) => [k, label, counts[k] ?? null])} />
          <div className="ad-toolbar-right">
            <Search value={term} onChange={setTerm} placeholder="Name, pattern or words" />
            <button className="ad-btn ad-primary" onClick={() => setEditing({})}>
              <Icon n="plus" size={16} />New answer
            </button>
          </div>
        </div>

        {error && <Empty icon="info" title="We could not reach the shop"
          text={error.message} action="Try again" onAction={reload} />}
        {loading && !rows.length && !error && (
          <Empty icon="chat" title="Loading…" text="Fetching the answers." />
        )}

        {!error && !!rows.length && (
          <ul className="ad-answers">
            {rows.map((a, i) => (
              <li key={a.id} style={{ "--i": i }} className={a.active ? "" : "ad-answer-off"}>
                <div className="ad-answer-body">
                  <div className="ad-answer-top">
                    <b>{a.title}</b>
                    <Pill s={a.active ? "on" : "off"} map={STATE_TONE} />
                    <span className="ad-answer-kind">{a.kindLabel}</span>
                  </div>
                  <code className="ad-answer-pattern">{a.pattern}</code>
                  <p>{a.reply || <em>worked out from their own orders</em>}</p>
                </div>
                <div className="ad-answer-act">
                  {canReorder && (
                    <div className="ad-answer-move">
                      <button className="ad-btn ad-sm" disabled={act.busy || i === 0}
                        aria-label="Try this earlier" onClick={() => move(i, -1)}>
                        <Icon n="up" size={14} />
                      </button>
                      <button className="ad-btn ad-sm" disabled={act.busy || i === rows.length - 1}
                        aria-label="Try this later" onClick={() => move(i, 1)}>
                        <Icon n="down" size={14} />
                      </button>
                    </div>
                  )}
                  <button className="ad-btn ad-sm" disabled={act.busy}
                    onClick={() => setEditing(a)}>Edit</button>
                  {a.active
                    ? <button className="ad-btn ad-sm" disabled={act.busy}
                      onClick={() => setDrop(a)}>Switch off</button>
                    : <button className="ad-btn ad-sm" disabled={act.busy}
                      onClick={() => switchIt(a, true)}>Put back</button>}
                </div>
              </li>
            ))}
          </ul>
        )}

        {!loading && !rows.length && !error && (
          <Empty icon="chat" title="Nothing here"
            text="No answer matches that. Try another tab, or clear the search." />
        )}

        {!canReorder && !!rows.length && (
          <p className="ad-hint ad-answer-hint">
            Open <b>All</b> with the search cleared to change which answer the
            bot tries first.
          </p>
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
        <AnswerDrawer answer={editing.id ? editing : null} kinds={kinds} flash={flash}
          onClose={() => setEditing(null)}
          onSaved={async (msg) => { setEditing(null); await reload(); flash?.(msg); }} />
      )}

      {drop && (
        <Confirm danger title="Switch this answer off?" confirmLabel="Switch it off"
          text={`The bot stops using “${drop.title}”. It is kept, not deleted — you can put it back at any time.`}
          onCancel={() => setDrop(null)}
          onConfirm={() => { const a = drop; setDrop(null); switchIt(a, false); }} />
      )}
    </div>
  );
}
