"use client";
/* ==========================================================================
   369 Mart — Admin · Home pages

   One card per saved page. Exactly one is the everyday page; any of them can
   be given a window, and during that window it takes over. The state on each
   card is the thing that must never be ambiguous, so it is the loudest part
   of it: an editor should never have to wonder whether shoppers can see what
   they are looking at.

   Every write goes to the shop and then re-reads. Nothing here patches a
   local copy to look like it worked.
   ========================================================================== */
import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { useAction, useResource } from "@/lib/useFetch";
import { Confirm, Drawer, Empty, Icon } from "./AdminUI";

const STATE = {
  live: { label: "Live now", tone: "green" },
  scheduled: { label: "Scheduled", tone: "blue" },
  ended: { label: "Ended", tone: "grey" },
  off: { label: "Off", tone: "grey" },
};

/* A datetime-local input wants "YYYY-MM-DDTHH:mm" and the shop speaks ISO. */
const toInput = (iso) => (iso ? iso.slice(0, 16) : "");
const toIso = (v) => (v ? v.replace("T", " ") + ":00" : false);

/* "What shall we call it?"
   A page called "Everyday (copy)" that somebody meant to call "Diwali" is a
   page nobody renames until they go looking for it six months later. */
function NamePrompt({ onCancel, onConfirm }) {
  const [name, setName] = useState("");
  const go = () => { if (name.trim()) onConfirm(name.trim()); };
  return (
    <Confirm
      title="What is this page for?"
      confirmLabel="Create page"
      onCancel={onCancel}
      onConfirm={go}
      text={
        <>
          <label className="ad-field ad-name-field">
            <span>Name</span>
            <input autoFocus value={name} placeholder="Diwali"
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") go(); }} />
          </label>
          It starts as a copy of the page that is on today, so you are editing
          something rather than building from nothing.
        </>
      } />
  );
}

/* Removed pages wait here. Mirrors the band Trash in the page editor, which
   is where an editor will have met this idea already. */
function TrashDrawer({ rows, days, busy, onRestore, onForget, onClose }) {
  return (
    <Drawer title="Trash" onClose={onClose}
      sub={rows.length
        ? `${rows.length} removed ${rows.length === 1 ? "page" : "pages"}`
        : "Nothing removed"}>
      {!rows.length ? (
        <Empty icon="trash" title="The Trash is empty"
          text="A page you remove waits here before it is deleted for good." />
      ) : (
        <>
          <p className="ad-hint ad-trash-note"><Icon n="info" size={14} />
            {days
              ? `A removed page waits ${days} days here, then goes for good. Putting one back returns it exactly as it was.`
              : "Removed pages are kept until you delete them for good."}
          </p>
          <ul className="ad-trash-list">
            {rows.map((page) => (
              <li key={page.id}>
                <span className="ad-trash-txt">
                  <b>{page.name}</b>
                  <small>
                    Removed {page.deletedAt ? page.deletedAt.slice(0, 16) : ""}
                    {days ? ` · ${page.daysLeft} day${page.daysLeft === 1 ? "" : "s"} left` : ""}
                  </small>
                </span>
                <button className="ad-btn ad-sm" disabled={busy}
                  onClick={() => onRestore(page)}>Put back</button>
                <button className="ad-btn ad-sm ad-danger-ghost" disabled={busy}
                  onClick={() => onForget(page)}>Delete for good</button>
              </li>
            ))}
          </ul>
        </>
      )}
    </Drawer>
  );
}

function PageCard({ page, i, busy, onSwitch, onSchedule, onDuplicate, onDelete, onEdit }) {
  const [open, setOpen] = useState(false);
  const [from, setFrom] = useState(toInput(page.startsOn));
  const [until, setUntil] = useState(toInput(page.endsOn));
  const bands = page.bands?.quick || {};
  const state = STATE[page.state] || STATE.off;

  return (
    <article className="ad-card ad-page-card" style={{ "--i": i }}>
      <header className="ad-card-head">
        <div>
          <h2>{page.name}</h2>
          <p>{page.stateNote}</p>
        </div>
        <span className={"ad-pill ad-t-" + state.tone}><i />{state.label}</span>
      </header>

      <p className="ad-page-bands">
        {bands.banners || 0} banners · {bands.tiles || 0} tiles ·{" "}
        {bands.tabs || 0} tabs · {bands.sections || 0} rows
      </p>

      <div className="ad-page-act">
        <button className="ad-btn ad-primary" onClick={() => onEdit(page)}>
          <Icon n="layers" size={15} />Edit page
        </button>
        <button className="ad-btn" disabled={page.isCurrent || busy}
          onClick={() => onSwitch(page)}
          title={page.isCurrent ? "This is the everyday page" : "Make this the everyday page"}>
          {page.isCurrent ? "Everyday page" : "Switch on"}
        </button>
        <button className="ad-btn" onClick={() => setOpen((v) => !v)}>
          {page.startsOn || page.endsOn ? "Change dates" : "Schedule"}
        </button>
        <span className="ad-page-more">
          <button className="ad-link" onClick={() => onDuplicate(page)} disabled={busy}>Duplicate</button>
          <button className="ad-link ad-danger-link" onClick={() => onDelete(page)}
            disabled={busy || page.isCurrent}>Remove</button>
        </span>
      </div>

      {open && (
        <div className="ad-sched">
          <div className="ad-form">
            <label className="ad-field"><span>Show from</span>
              <input type="datetime-local" value={from} onChange={(e) => setFrom(e.target.value)} /></label>
            <label className="ad-field"><span>Show until</span>
              <input type="datetime-local" value={until} onChange={(e) => setUntil(e.target.value)} /></label>
          </div>
          <p className="ad-hint"><Icon n="info" size={14} />
            During this window it takes over. When it ends, the everyday page
            comes back on its own — nobody has to be awake for either.
          </p>
          <div className="ad-sched-act">
            <button className="ad-btn" disabled={busy}
              onClick={() => { setFrom(""); setUntil(""); onSchedule(page, null, null); setOpen(false); }}>
              Clear dates
            </button>
            <button className="ad-btn ad-primary" disabled={busy}
              onClick={() => { onSchedule(page, from, until); setOpen(false); }}>
              Save dates
            </button>
          </div>
        </div>
      )}
    </article>
  );
}

export default function HomeSection({ flash }) {
  const router = useRouter();
  const { data, loading, error, reload } = useResource("/admin/home/pages");
  const act = useAction();
  const [confirm, setConfirm] = useState(null);
  const [switching, setSwitching] = useState(null);
  const [naming, setNaming] = useState(false);
  const [forget, setForget] = useState(null);
  const [trashOpen, setTrashOpen] = useState(false);
  const pages = data?.pages || [];
  const trash = data?.trash || [];
  const trashDays = data?.trash_days ?? 0;
  /* Whichever page shoppers are on right now - not necessarily the one
     flagged everyday, because an open window beats the flag. */
  const live = pages.find((p) => p.state === "live");

  const run = (fn, ok) =>
    act.run(async () => {
      const r = await fn();
      api.invalidate("/admin/home");
      await reload();
      flash?.(ok);
      return r ?? true;
    }).then((r) => {
      if (r === null) flash?.(act.error?.message || "That did not work.", "bad");
      return r;
    });

  const onSwitch = (page) =>
    run(() => api(`/admin/home/pages/${page.id}/current`, { method: "POST" }),
      `“${page.name}” is now the everyday page`);

  const onSchedule = (page, from, until) =>
    run(() => api(`/admin/home/pages/${page.id}`, {
      method: "PATCH", body: { startsOn: toIso(from), endsOn: toIso(until) },
    }), from || until ? `“${page.name}” is scheduled` : "Dates cleared");

  const onDuplicate = (page, name) =>
    run(() => api("/admin/home/pages", {
      method: "POST", body: { from: page.id, ...(name ? { name } : {}) },
    }), name
      ? `“${name}” created. Edit it, then switch it on when you are ready.`
      : "Copied. Edit it, then switch it on when you are ready.");

  const onDelete = (page) =>
    run(() => api(`/admin/home/pages/${page.id}`, { method: "DELETE" }),
      `“${page.name}” moved to the Trash`);

  const onRestore = (page) =>
    run(() => api(`/admin/home/pages/${page.id}/restore`, { method: "POST" }),
      `“${page.name}” is back`);

  /* Gone now rather than in thirty days. Only reachable from the Trash, so
     nothing is destroyed without having been visible there first. */
  const onForget = (page) =>
    run(() => api(`/admin/home/pages/${page.id}/forever`, { method: "DELETE" }),
      `“${page.name}” deleted`);

  return (
    <div className="ad-stack">
      <section className="ad-card">
        <header className="ad-card-head">
          <div>
            <h2>Saved home pages</h2>
            <p>Build a page once, switch it on when you need it — or give it
              dates and let it switch itself.</p>
          </div>
          <div className="ad-head-act">
            <button className="ad-btn" disabled={act.busy}
              onClick={() => setTrashOpen(true)}>
              <Icon n="trash" size={15} />Trash{trash.length ? <em>{trash.length}</em> : null}
            </button>
            <button className="ad-btn ad-primary" disabled={act.busy || !pages.length}
              onClick={() => setNaming(true)}>
              <Icon n="plus" size={15} />New page
            </button>
          </div>
        </header>
        <p className="ad-hint ad-form-pad"><Icon n="info" size={14} />
          Whichever page is scheduled right now is what shoppers see; otherwise
          the everyday one is.
        </p>
      </section>

      {error && (
        <section className="ad-card">
          <Empty icon="info" title="We could not reach the shop"
            text={error.message} action="Try again" onAction={reload} />
        </section>
      )}

      {loading && !pages.length && !error && (
        <section className="ad-card"><Empty icon="layers" title="Loading…" text="Fetching your saved pages." /></section>
      )}

      <div className="ad-page-grid">
        {pages.map((p, i) => (
          <PageCard key={p.id} page={p} i={i} busy={act.busy}
            onSwitch={(page) => setSwitching(page)}
            onSchedule={onSchedule} onDuplicate={onDuplicate}
            onDelete={(page) => setConfirm(page)}
            onEdit={(page) => router.push(`/admin/home/${page.id}`)} />
        ))}
      </div>

      {!loading && !pages.length && !error && (
        <section className="ad-card">
          <Empty icon="layers" title="No saved pages yet"
            text="Install the home page module's demo data, or make one in Odoo." />
        </section>
      )}

      {confirm && (
        <Confirm danger title={`Remove “${confirm.name}”?`}
          text={trashDays
            ? `It goes to the Trash, where you can put it back for ${trashDays} days.`
            : "It goes to the Trash, where you can put it back."}
          confirmLabel="Remove page"
          onCancel={() => setConfirm(null)}
          onConfirm={() => { const p = confirm; setConfirm(null); onDelete(p); }} />
      )}

      {/* Switching is what shoppers see change, so it says which page they
          are on now and which they will be on. */}
      {switching && (
        <Confirm
          title={live && live.id !== switching.id
            ? `Switch from “${live.name}” to “${switching.name}”?`
            : `Switch on “${switching.name}”?`}
          text={live && live.id !== switching.id
            ? `Shoppers are on “${live.name}”. They will be on “${switching.name}” straight away.`
            : `Shoppers will be on “${switching.name}” straight away.`}
          confirmLabel="Switch on"
          onCancel={() => setSwitching(null)}
          onConfirm={() => { const p = switching; setSwitching(null); onSwitch(p); }} />
      )}

      {naming && (
        <NamePrompt
          onCancel={() => setNaming(false)}
          onConfirm={(name) => {
            setNaming(false);
            onDuplicate(pages.find((p) => p.isCurrent) || pages[0], name);
          }} />
      )}

      {forget && (
        <Confirm danger title={`Delete “${forget.name}” for good?`}
          text="It and everything on it goes now. There is no putting it back."
          confirmLabel="Delete for good"
          onCancel={() => setForget(null)}
          onConfirm={() => { const p = forget; setForget(null); onForget(p); }} />
      )}

      {trashOpen && (
        <TrashDrawer rows={trash} days={trashDays} busy={act.busy}
          onRestore={onRestore} onForget={(page) => setForget(page)}
          onClose={() => setTrashOpen(false)} />
      )}
    </div>
  );
}
