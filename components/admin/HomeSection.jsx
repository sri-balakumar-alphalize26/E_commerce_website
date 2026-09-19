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
import { Confirm, Empty, Icon } from "./AdminUI";

const STATE = {
  live: { label: "Live now", tone: "green" },
  scheduled: { label: "Scheduled", tone: "blue" },
  ended: { label: "Ended", tone: "grey" },
  off: { label: "Off", tone: "grey" },
};

/* A datetime-local input wants "YYYY-MM-DDTHH:mm" and the shop speaks ISO. */
const toInput = (iso) => (iso ? iso.slice(0, 16) : "");
const toIso = (v) => (v ? v.replace("T", " ") + ":00" : false);

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
            disabled={busy || page.isCurrent}>Delete</button>
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
  const pages = data?.pages || [];

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

  const onDuplicate = (page) =>
    run(() => api("/admin/home/pages", { method: "POST", body: { from: page.id } }),
      "Copied. Edit it, then switch it on when you are ready.");

  const onDelete = (page) =>
    run(() => api(`/admin/home/pages/${page.id}`, { method: "DELETE" }),
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
          <button className="ad-btn ad-primary" disabled={act.busy || !pages.length}
            onClick={() => onDuplicate(pages.find((p) => p.isCurrent) || pages[0])}>
            <Icon n="plus" size={15} />New page
          </button>
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
            onSwitch={onSwitch} onSchedule={onSchedule} onDuplicate={onDuplicate}
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
        <Confirm danger title={`Delete “${confirm.name}”?`}
          text="Its banners, tabs, tiles and rows go with it. This cannot be undone."
          confirmLabel="Delete page"
          onCancel={() => setConfirm(null)}
          onConfirm={() => { const p = confirm; setConfirm(null); onDelete(p); }} />
      )}
    </div>
  );
}
