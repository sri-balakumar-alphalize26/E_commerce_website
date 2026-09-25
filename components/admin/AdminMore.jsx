"use client";
/* ==========================================================================
   369 Mart admin — Offers · Reviews · Settings
   ========================================================================== */
import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { api } from "@/lib/api";
import { money } from "@/lib/money";
import { useAction, useResource } from "@/lib/useFetch";
import { Avatar, Confirm, Drawer, Empty, Icon, Search, Select, Switch, Tabs } from "./AdminUI";
import { since } from "./format";

/* ================================ offers ================================
   Coupons, read and written in the shop.

   What a code is worth is not decided here and never was in the browser: the
   cart and the order both price it through `_mart369_discount` on the model.
   This screen sets the rules; the shop applies them.

   Switched on and usable are two different things, and the card says which.
   A code can be on and out of its window, or on and spent - both look
   identical on a switch, and both refuse the next customer who types it. */
const KINDS = {
  percent: { label: "Percentage off", unit: "%" },
  flat: { label: "Flat amount off", unit: "" },
  free_delivery: { label: "Free delivery", unit: "" },
};
const GROUPS = {
  "": "The whole basket",
  quick: "Quick items only",
  all: "Express items only",
};

const BLANK = {
  code: "", title: "", note: "", kind: "flat", value: "",
  max_off: "", min_spend: "", group: "", starts_on: "", ends_on: "",
  limit_total: "", limit_per_customer: "",
};

/* Doubles as the edit form: a coupon and a blank one differ only in whether
   there is an id to PATCH. */
function CouponForm({ coupon, currency, busy, error, onClose, onSave }) {
  const [f, setF] = useState(coupon ? {
    code: coupon.code, title: coupon.title, note: coupon.note,
    kind: coupon.kind, value: String(coupon.value || ""),
    max_off: String(coupon.maxOff || ""), min_spend: String(coupon.minSpend || ""),
    group: coupon.group || "", starts_on: coupon.startsOn || "",
    ends_on: coupon.endsOn || "", limit_total: String(coupon.limitTotal || ""),
    limit_per_customer: String(coupon.limitPerCustomer || ""),
  } : BLANK);

  const set = (k) => (e) => setF({
    ...f,
    /* A code is typed in a hurry and read off a poster. Upper-casing and
       dropping punctuation here means "onam 25" and "ONAM-25" cannot become
       two codes that look the same to a customer. */
    [k]: k === "code" ? e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, "") : e.target.value,
  });

  const free = f.kind === "free_delivery";
  const ok = f.code.length >= 3 && f.title.trim().length > 2 && (free || Number(f.value) > 0);

  return (
    <Drawer wide title={coupon ? `Edit ${coupon.code}` : "New coupon"}
      sub="Customers type it in the cart. The shop works out what it is worth."
      onClose={onClose}
      foot={(close) => (
        <>
          <button className="ad-btn" onClick={close}>Cancel</button>
          <button className="ad-btn ad-primary" disabled={!ok || busy}
            onClick={() => onSave(f)}>
            {coupon ? "Save changes" : "Create coupon"}
          </button>
        </>
      )}>
      {error && <p className="ad-hint ad-form-error" role="alert"><Icon n="info" size={14} />{error}</p>}
      <div className="ad-form">
        <label className="ad-field"><span>Code</span>
          <input value={f.code} onChange={set("code")} placeholder="ONAM25" /></label>
        <label className="ad-field"><span>Discount</span>
          <select value={f.kind} onChange={set("kind")}>
            {Object.entries(KINDS).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
          </select></label>

        <label className="ad-field ad-span2"><span>Title customers see</span>
          <input value={f.title} onChange={set("title")} placeholder="25% off cables" /></label>
        <label className="ad-field ad-span2"><span>Small print</span>
          <input value={f.note} onChange={set("note")} placeholder="Chargers, cables and adaptors" /></label>

        {!free && (
          <label className="ad-field">
            <span>{f.kind === "percent" ? "Per cent off" : "Amount off"}</span>
            <input inputMode="decimal" value={f.value} onChange={set("value")} /></label>
        )}
        {f.kind === "percent" && (
          <label className="ad-field"><span>Never more than</span>
            <input inputMode="decimal" value={f.max_off} onChange={set("max_off")}
              placeholder="0 for no cap" /></label>
        )}
        <label className="ad-field"><span>Minimum spend</span>
          <input inputMode="decimal" value={f.min_spend} onChange={set("min_spend")}
            placeholder="0 for none" /></label>
        <label className="ad-field"><span>Applies to</span>
          <select value={f.group} onChange={set("group")}>
            {Object.entries(GROUPS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select></label>

        <label className="ad-field"><span>Starts</span>
          <input type="date" value={f.starts_on} onChange={set("starts_on")} /></label>
        <label className="ad-field"><span>Ends</span>
          <input type="date" value={f.ends_on} onChange={set("ends_on")} /></label>

        <label className="ad-field"><span>Total uses allowed</span>
          <input inputMode="numeric" value={f.limit_total} onChange={set("limit_total")}
            placeholder="0 for no limit" /></label>
        <label className="ad-field"><span>Uses per customer</span>
          <input inputMode="numeric" value={f.limit_per_customer}
            onChange={set("limit_per_customer")} placeholder="0 for no limit" /></label>

        <p className="ad-hint ad-span2"><Icon n="info" size={14} />
          Leave the dates empty and it runs until you switch it off. How many
          times it has been used is the shop's to count — it goes up when a
          payment lands and back down if that order is cancelled.
        </p>
      </div>
    </Drawer>
  );
}

function worth(c, currency) {
  if (c.kind === "free_delivery") return "Free delivery";
  if (c.kind === "percent") {
    return `${c.value}% off` + (c.maxOff ? `, up to ${money(c.maxOff, currency)}` : "");
  }
  return `${money(c.value, currency)} off`;
}

/* Why a code is not usable, in the words an operator would use. Silence when
   it is fine — a card that explains itself when nothing is wrong is noise. */
function why(c) {
  if (!c.active) return "Paused";
  if (c.limitTotal && c.usedCount >= c.limitTotal) return "Used up";
  const today = new Date().toISOString().slice(0, 10);
  if (c.startsOn && today < c.startsOn) return `Starts ${c.startsOn}`;
  if (c.endsOn && today > c.endsOn) return `Ended ${c.endsOn}`;
  return "";
}

export function OffersSection({ flash }) {
  const { data, loading, error, reload } = useResource("/admin/coupons");
  const act = useAction();
  const [editing, setEditing] = useState(null);   // a coupon, or BLANK-ish {}
  const [confirm, setConfirm] = useState(null);
  const [formError, setFormError] = useState("");
  const [saving, setSaving] = useState(false);

  const coupons = data?.coupons || [];
  const counts = data?.counts || {};
  const currency = data?.currency;

  /* Read-after-write, like Orders. `live`, `usedCount` and the tile numbers
     are all the shop's, and guessing them is how a panel starts lying. */
  const run = (fn, ok) =>
    act.run(async () => {
      await fn();
      api.invalidate("/admin/coupons");
      await reload();
      if (ok) flash?.(ok);
      return true;
    }).then((r) => {
      if (r === null) flash?.(act.error?.message || "That did not work.", "bad");
      return r;
    });

  const onToggle = (c) =>
    run(() => api(`/admin/coupons/${c.id}`, { method: "PATCH", body: { active: !c.active } }),
      `${c.code} ${c.active ? "paused" : "switched on"}`);

  /* Its own try/catch rather than `run()`. The server names the field it is
     refusing - "there is already a coupon with the code CHECK10" - and that
     sentence has to reach the drawer. Reading `act.error` here would give the
     previous render's value, which is empty on the first failure. */
  const onSave = async (form) => {
    setFormError("");
    setSaving(true);
    try {
      await api(
        editing?.id ? `/admin/coupons/${editing.id}` : "/admin/coupons",
        { method: editing?.id ? "PATCH" : "POST", body: { ...form } },
      );
      api.invalidate("/admin/coupons");
      await reload();
      setEditing(null);
      flash?.(editing?.id ? `${form.code} saved` : `${form.code} created`);
    } catch (e) {
      /* The drawer stays open with the message in it. Closing it and
         flashing would throw away everything just typed. */
      setFormError(e?.message || "That could not be saved.");
    } finally {
      setSaving(false);
    }
  };

  const onDelete = (c) =>
    run(() => api(`/admin/coupons/${c.id}`, { method: "DELETE" }), `${c.code} deleted`);

  return (
    <div className="ad-stack">
      <section className="ad-mini-stats">
        <span><small>Coupons</small><b>{counts.all ?? 0}</b></span>
        <span><small>Usable now</small><b>{counts.live ?? 0}</b></span>
        <span><small>Redemptions</small><b>{data?.redemptions ?? 0}</b></span>
        <span className="ad-warn"><small>Nearly used up</small><b>{counts.nearlyUsedUp ?? 0}</b></span>
      </section>

      <section className="ad-card">
        <div className="ad-toolbar">
          <div><h2 className="ad-sec-h">Coupons</h2></div>
          <div className="ad-toolbar-right">
            <button className="ad-btn ad-primary" disabled={act.busy}
              onClick={() => { setFormError(""); setEditing({}); }}>
              <Icon n="plus" size={16} />New coupon
            </button>
          </div>
        </div>

        {error && (
          <Empty icon="info" title="We could not reach the shop" text={error.message}
            action="Try again" onAction={reload} />
        )}
        {loading && !coupons.length && !error && (
          <Empty icon="ticket" title="Loading…" text="Fetching your coupons." />
        )}
        {!loading && !coupons.length && !error && (
          <Empty icon="ticket" title="No coupons yet"
            text="Make one and customers can type it in the cart." />
        )}

        {!error && !!coupons.length && (
          <div className="ad-coupons">
            {coupons.map((c, i) => {
              const pct = c.limitTotal
                ? Math.min(100, Math.round((c.usedCount / c.limitTotal) * 100)) : 0;
              const stopped = why(c);
              return (
                <article key={c.id} className={"ad-coupon" + (c.live ? "" : " ad-off")}
                  style={{ "--i": i }}>
                  <span className="ad-coupon-stub"><Icon n="pct" size={18} /><b>{c.code}</b></span>
                  <div className="ad-coupon-body">
                    <b>{c.title}</b>
                    <small>{worth(c, currency)}{c.minSpend ? ` · over ${money(c.minSpend, currency)}` : ""}
                      {c.group ? ` · ${GROUPS[c.group]}` : ""}</small>
                    {c.note && <small>{c.note}</small>}
                    {!!c.limitTotal && (
                      <div className="ad-progress" style={{ "--p": pct + "%" }} role="img"
                        aria-label={`${c.usedCount} of ${c.limitTotal} used`}><i /></div>
                    )}
                    <small className="ad-coupon-use">
                      {c.limitTotal
                        ? `${c.usedCount} of ${c.limitTotal} used`
                        : `${c.usedCount} used`}
                      {stopped ? ` · ${stopped}` : c.endsOn ? ` · until ${c.endsOn}` : ""}
                    </small>
                  </div>
                  <div className="ad-coupon-act">
                    <Switch on={c.active} onChange={() => onToggle(c)} label={`${c.code} active`} />
                    <button className="ad-link" disabled={act.busy}
                      onClick={() => { setFormError(""); setEditing(c); }}>Edit</button>
                    <button className="ad-link" onClick={() => {
                      navigator.clipboard?.writeText(c.code); flash(`${c.code} copied`);
                    }}>Copy</button>
                    <button className="ad-link ad-danger-link" disabled={act.busy}
                      onClick={() => setConfirm(c)}>Delete</button>
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </section>

      {editing && (
        <CouponForm coupon={editing.id ? editing : null} currency={currency}
          busy={saving} error={formError}
          onClose={() => setEditing(null)} onSave={onSave} />
      )}

      <DealsBlock flash={flash} />

      {confirm && (
        <Confirm danger title={`Delete ${confirm.code}?`}
          text={confirm.usedCount
            ? `It has been used ${confirm.usedCount} times, so the shop will keep it and ask you to switch it off instead.`
            : "Nobody has used it, so it goes for good."}
          confirmLabel="Delete coupon"
          onCancel={() => setConfirm(null)}
          onConfirm={() => { const c = confirm; setConfirm(null); onDelete(c); }} />
      )}
    </div>
  );
}

/* ================================= deals ================================
   A price cut on chosen products, for a window.

   The opposite of a coupon: nobody types anything, the card is simply
   cheaper. Nothing is written to the product either - the lower price is
   worked out whenever a card, a basket or an order is priced - so switching
   a deal off puts every price back on its own. */
const DEAL_KINDS = { percent: "Percentage off", amount: "Amount off" };

const BLANK_DEAL = {
  name: "", note: "", kind: "percent", value: "", floor: "",
  starts_on: "", ends_on: "", product_ids: [],
};

/* Odoo speaks "YYYY-MM-DD HH:MM:SS"; a datetime-local input wants a T. */
const toLocal = (v) => (v ? v.slice(0, 16).replace(" ", "T") : "");

function DealForm({ deal, busy, error, onClose, onSave }) {
  const [f, setF] = useState(deal ? {
    name: deal.name, note: deal.note, kind: deal.kind,
    value: String(deal.value || ""), floor: String(deal.floor || ""),
    starts_on: toLocal(deal.startsOn), ends_on: toLocal(deal.endsOn),
    product_ids: deal.products.map((p) => p.id),
  } : BLANK_DEAL);
  const [picked, setPicked] = useState(deal ? deal.products : []);
  const [term, setTerm] = useState("");
  const [found, setFound] = useState([]);

  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  /* Searched in the shop, not filtered here - a catalogue does not fit in
     the browser. Same 300ms as everywhere else in the console. */
  useEffect(() => {
    const q = term.trim();
    if (!q) { setFound([]); return undefined; }
    const id = setTimeout(async () => {
      try {
        const r = await api(`/admin/deals/products?q=${encodeURIComponent(q)}`);
        setFound(r.products || []);
      } catch { setFound([]); }
    }, 300);
    return () => clearTimeout(id);
  }, [term]);

  const add = (p) => {
    if (picked.some((x) => x.id === p.id)) return;
    const next = [...picked, p];
    setPicked(next);
    setF((v) => ({ ...v, product_ids: next.map((x) => x.id) }));
    setTerm("");
    setFound([]);
  };
  const drop = (id) => {
    const next = picked.filter((x) => x.id !== id);
    setPicked(next);
    setF((v) => ({ ...v, product_ids: next.map((x) => x.id) }));
  };

  const ok = f.name.trim().length > 1 && picked.length > 0 && Number(f.value) > 0;

  return (
    <Drawer wide title={deal ? `Edit ${deal.name}` : "New deal"}
      sub="Shoppers see the lower price straight away. They do not type anything."
      onClose={onClose}
      foot={(close) => (
        <>
          <button className="ad-btn" onClick={close}>Cancel</button>
          <button className="ad-btn ad-primary" disabled={!ok || busy}
            onClick={() => onSave(f)}>{deal ? "Save changes" : "Create deal"}</button>
        </>
      )}>
      {error && <p className="ad-hint ad-form-error" role="alert"><Icon n="info" size={14} />{error}</p>}
      <div className="ad-form">
        <label className="ad-field ad-span2"><span>Name</span>
          <input value={f.name} onChange={set("name")} placeholder="Diwali weekend" /></label>
        <label className="ad-field ad-span2"><span>Note</span>
          <input value={f.note} onChange={set("note")}
            placeholder="A line for whoever opens this in six months" /></label>

        <label className="ad-field"><span>Discount</span>
          <select value={f.kind} onChange={set("kind")}>
            {Object.entries(DEAL_KINDS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select></label>
        <label className="ad-field">
          <span>{f.kind === "percent" ? "Per cent off" : "Amount off"}</span>
          <input inputMode="decimal" value={f.value} onChange={set("value")} /></label>
        <label className="ad-field"><span>Never below</span>
          <input inputMode="decimal" value={f.floor} onChange={set("floor")}
            placeholder="0 for no floor" /></label>
        <label className="ad-field"><span>Starts</span>
          <input type="datetime-local" value={f.starts_on} onChange={set("starts_on")} /></label>
        <label className="ad-field"><span>Ends</span>
          <input type="datetime-local" value={f.ends_on} onChange={set("ends_on")} /></label>

        <div className="ad-field ad-span2">
          <span>Products <em className="ad-dim">{picked.length} picked</em></span>
          <input value={term} onChange={(e) => setTerm(e.target.value)}
            placeholder="Search the catalogue" />
          {!!found.length && (
            <ul className="ad-pick-results">
              {found.map((p) => (
                <li key={p.id}>
                  <button type="button" onClick={() => add(p)}>
                    {p.name}<small>{p.price}</small>
                  </button>
                </li>
              ))}
            </ul>
          )}
          <div className="ad-picked">
            {picked.map((p) => (
              <span key={p.id} className="ad-chip">
                {p.name}
                <button type="button" aria-label={`Remove ${p.name}`}
                  onClick={() => drop(p.id)}>×</button>
              </span>
            ))}
          </div>
        </div>

        <p className="ad-hint ad-span2"><Icon n="info" size={14} />
          Leave the dates empty and it runs until you switch it off. A product
          caught by two deals takes the better one, never both.
        </p>
      </div>
    </Drawer>
  );
}

export function DealsBlock({ flash }) {
  const { data, loading, error, reload } = useResource("/admin/deals");
  const act = useAction();
  const [editing, setEditing] = useState(null);
  const [confirm, setConfirm] = useState(null);
  const [forget, setForget] = useState(null);
  const [trashOpen, setTrashOpen] = useState(false);
  const [formError, setFormError] = useState("");
  const [saving, setSaving] = useState(false);

  const deals = data?.deals || [];
  const trash = data?.trash || [];
  const trashDays = data?.trashDays ?? 0;
  const counts = data?.counts || {};
  const currency = data?.currency;

  const run = (fn, ok) =>
    act.run(async () => {
      await fn();
      api.invalidate("/admin/deals");
      await reload();
      if (ok) flash?.(ok);
      return true;
    }).then((r) => {
      if (r === null) flash?.(act.error?.message || "That did not work.", "bad");
      return r;
    });

  const onSave = async (form) => {
    setFormError("");
    setSaving(true);
    try {
      await api(editing?.id ? `/admin/deals/${editing.id}` : "/admin/deals", {
        method: editing?.id ? "PATCH" : "POST", body: { ...form },
      });
      api.invalidate("/admin/deals");
      await reload();
      setEditing(null);
      flash?.(editing?.id ? `${form.name} saved` : `${form.name} created`);
    } catch (e) {
      setFormError(e?.message || "That could not be saved.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <section className="ad-mini-stats">
        <span><small>Deals</small><b>{counts.all ?? 0}</b></span>
        <span><small>On right now</small><b>{counts.live ?? 0}</b></span>
        <span><small>Starting later</small><b>{counts.scheduled ?? 0}</b></span>
        <span><small>Products on offer</small><b>{data?.onOffer ?? 0}</b></span>
      </section>

      <section className="ad-card">
        <div className="ad-toolbar">
          <div><h2 className="ad-sec-h">Deals</h2></div>
          <div className="ad-toolbar-right">
            <button className="ad-btn" disabled={act.busy}
              onClick={() => setTrashOpen(true)}>
              <Icon n="trash" size={16} />Trash{trash.length ? <em>{trash.length}</em> : null}
            </button>
            <button className="ad-btn ad-primary" disabled={act.busy}
              onClick={() => { setFormError(""); setEditing({}); }}>
              <Icon n="plus" size={16} />New deal
            </button>
          </div>
        </div>

        {error && (
          <Empty icon="info" title="We could not reach the shop" text={error.message}
            action="Try again" onAction={reload} />
        )}
        {loading && !deals.length && !error && (
          <Empty icon="pct" title="Loading…" text="Fetching your deals." />
        )}
        {!loading && !deals.length && !error && (
          <Empty icon="pct" title="No deals yet"
            text="Put some products on offer and the price drops on the card, in the basket and on the order." />
        )}

        {!error && !!deals.length && (
          <ul className="ad-deals">
            {deals.map((d, i) => (
              <li key={d.id} className={d.live ? "" : "ad-off"} style={{ "--i": i }}>
                <span className="ad-deal-body">
                  <b>{d.name}</b>
                  <small>
                    {d.kind === "percent" ? `${d.value}% off` : `${money(d.value, currency)} off`}
                    {" · "}{d.productCount} product{d.productCount === 1 ? "" : "s"}
                    {d.floor ? ` · never below ${money(d.floor, currency)}` : ""}
                  </small>
                  <small className="ad-dim">
                    {!d.active ? "Switched off"
                      : d.live ? (d.endsOn ? `On now, until ${d.endsOn.slice(0, 16)}` : "On now")
                        : d.startsOn ? `Starts ${d.startsOn.slice(0, 16)}` : "Ended"}
                  </small>
                </span>
                <span className="ad-deal-act">
                  <Switch on={d.active} label={`${d.name} active`}
                    onChange={() => run(
                      () => api(`/admin/deals/${d.id}`, { method: "PATCH", body: { active: !d.active } }),
                      `${d.name} ${d.active ? "switched off" : "switched on"}`)} />
                  <button className="ad-link" disabled={act.busy}
                    onClick={() => { setFormError(""); setEditing(d); }}>Edit</button>
                  <button className="ad-link ad-danger-link" disabled={act.busy}
                    onClick={() => setConfirm(d)}>Remove</button>
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      {editing && (
        <DealForm deal={editing.id ? editing : null} busy={saving} error={formError}
          onClose={() => setEditing(null)} onSave={onSave} />
      )}

      {confirm && (
        <Confirm danger title={`Remove ${confirm.name}?`}
          text={trashDays
            ? `It stops discounting straight away and waits in the Trash for ${trashDays} days, where you can put it back.`
            : "It stops discounting straight away and waits in the Trash, where you can put it back."}
          confirmLabel="Remove deal"
          onCancel={() => setConfirm(null)}
          onConfirm={() => {
            const d = confirm; setConfirm(null);
            run(() => api(`/admin/deals/${d.id}`, { method: "DELETE" }),
              `${d.name} moved to the Trash`);
          }} />
      )}

      {forget && (
        <Confirm danger title={`Delete ${forget.name} for good?`}
          text="Orders already placed keep the price they were charged — it was frozen onto the line at the time — so only this record goes."
          confirmLabel="Delete for good"
          onCancel={() => setForget(null)}
          onConfirm={() => {
            const d = forget; setForget(null);
            run(() => api(`/admin/deals/${d.id}/forever`, { method: "DELETE" }),
              `${d.name} deleted`);
          }} />
      )}

      {trashOpen && (
        <Drawer title="Trash" onClose={() => setTrashOpen(false)}
          sub={trash.length
            ? `${trash.length} removed ${trash.length === 1 ? "deal" : "deals"}`
            : "Nothing removed"}>
          {!trash.length ? (
            <Empty icon="trash" title="The Trash is empty"
              text="A deal you remove waits here before it is deleted for good." />
          ) : (
            <>
              <p className="ad-hint ad-trash-note"><Icon n="info" size={14} />
                {trashDays
                  ? `A removed deal stops discounting at once and waits ${trashDays} days here, then goes for good. Putting one back returns it exactly as it was — switched off if it was switched off.`
                  : "Removed deals stop discounting at once and are kept until you delete them for good."}
              </p>
              <ul className="ad-trash-list">
                {trash.map((d) => (
                  <li key={d.id}>
                    <span className="ad-trash-txt">
                      <b>{d.name}</b>
                      <small>
                        {d.kind === "percent" ? `${d.value}% off` : `${money(d.value, currency)} off`}
                        {" · "}{d.productCount} product{d.productCount === 1 ? "" : "s"}
                        {" · removed "}{d.deletedAt ? d.deletedAt.slice(0, 16) : ""}
                        {trashDays ? ` · ${d.daysLeft} day${d.daysLeft === 1 ? "" : "s"} left` : ""}
                      </small>
                    </span>
                    <button className="ad-btn ad-sm" disabled={act.busy}
                      onClick={() => run(
                        () => api(`/admin/deals/${d.id}/restore`, { method: "POST" }),
                        `${d.name} is back`)}>Put back</button>
                    <button className="ad-btn ad-sm ad-danger-ghost" disabled={act.busy}
                      onClick={() => setForget(d)}>Delete for good</button>
                  </li>
                ))}
              </ul>
            </>
          )}
        </Drawer>
      )}
    </>
  );
}

/* =============================== reviews ================================
   Moderation, read and written in the shop - the twin of the Odoo Reviews
   desk (mart369_account review_desk), which works the same three model
   methods: publish or hide with a reason, reply, approve or remove a photo.

   Every review is published the moment it is written, unless the word filter
   holds it (a phone number, a link, a blocked word) or shoppers report it
   three times - those wait, with the reason on a chip. Waiting is a list to
   read afterwards rather than a gate to pass.

   Staff never edit a review's words or stars. They decide whether it shows,
   reply to it in public, and approve or remove its photos. */
const REVIEW_TONE = (s) => (s >= 4 ? "ad-a-green" : s >= 3 ? "ad-a-orange" : "ad-a-red");
const mediaSrc = (m) => (m.url || "").replace(/^\/369mart\//, "/api/mart/");

/* One review, opened: everything about it, and every action on it. */
function ReviewDrawer({ review: start, hideReasons, onClose, onChanged }) {
  const [r, setR] = useState(start);
  const [reply, setReply] = useState(start.reply || "");
  const [reason, setReason] = useState(hideReasons?.[0] || "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [removing, setRemoving] = useState(null);

  const call = async (path, body, ok) => {
    setBusy(true); setError("");
    try {
      const res = await api(path, { method: "POST", body });
      setR(res.review);
      setReply(res.review.reply || "");
      onChanged(ok);
      return true;
    } catch (e) {
      setError(e.message || "That did not work.");
      return false;
    } finally {
      setBusy(false);
    }
  };
  const moderate = (state) => call(`/admin/reviews/${r.id}/moderate`, state === "hidden" ? { state, reason } : { state },
    state === "hidden" ? "Review hidden" : "Review published");

  return (
    <>
      <Drawer title={r.title || "No headline"} sub={`${r.by} · ${r.product} · ${since(r.at)}`} onClose={onClose}
        foot={(close) => (
          <>
            {r.state !== "hidden" && (
              <span className="ad-rev-hide">
                <Select value={reason} onChange={setReason} label="Why hide it"
                  options={(hideReasons || []).map((x) => [x, x])} />
                <button className="ad-btn ad-danger-ghost" disabled={busy || !reason} onClick={() => moderate("hidden")}>Hide</button>
              </span>
            )}
            {r.state !== "published" && (
              <button className="ad-btn ad-primary" disabled={busy} onClick={() => moderate("published")}>Publish</button>
            )}
            <button className="ad-btn" onClick={close}>Close</button>
          </>
        )}>
        {error && <p className="ad-form-error" role="alert">{error}</p>}

        <section className="ad-dsec">
          <div className="ad-review-top">
            <span className={"ad-stars ad-s" + r.stars}>{r.stars}★</span>
            {r.verified && <span className="ad-pill ad-t-green">Verified buyer</span>}
            <span className={"ad-pill ad-t-" + (r.state === "published" ? "green" : r.state === "hidden" ? "grey" : "amber")}>
              {r.state === "published" ? "Published" : r.state === "hidden" ? "Hidden" : "Waiting"}
            </span>
          </div>
          <p className="ad-rev-text">{r.text || "No words - stars only."}</p>
          {!!r.tags?.length && <p className="ad-rev-tags">{r.tags.map((t) => <span key={t} className="ad-pill ad-t-blue">{t}</span>)}</p>}
          <p className="ad-hint">
            {r.helpful ? `${r.helpful} found it helpful` : "Nobody has marked it helpful yet"}
            {r.reports ? ` · reported ${r.reports}×` : ""}
          </p>
          {r.heldReason && r.state === "pending" && <p className="ad-risk-line"><Icon n="info" size={14} />Held because: {r.heldReason}</p>}
          {r.hiddenReason && r.state === "hidden" && <p className="ad-risk-line"><Icon n="info" size={14} />Hidden because: {r.hiddenReason}</p>}
        </section>

        {!!r.media?.length && (
          <section className="ad-dsec">
            <h4>Photos &amp; videos <em>{r.media.length}</em></h4>
            <ul className="ad-rev-media">
              {r.media.map((m) => (
                <li key={m.id}>
                  {m.kind === "video"
                    ? <video src={mediaSrc(m)} controls preload="metadata" />
                    : <img src={mediaSrc(m)} alt="Customer photo" />}
                  <span className={"ad-pill ad-t-" + (m.state === "approved" ? "green" : "amber")}>{m.state === "approved" ? "Shown" : "Waiting"}</span>
                  <span className="ad-rev-media-act">
                    {m.state !== "approved" && (
                      <button className="ad-btn ad-sm ad-primary" disabled={busy}
                        onClick={() => call(`/admin/reviews/media/${m.id}`, { action: "approve" }, "Photo shown")}>Approve</button>
                    )}
                    <button className="ad-btn ad-sm ad-danger-ghost" disabled={busy} onClick={() => setRemoving(m)}>Remove</button>
                  </span>
                </li>
              ))}
            </ul>
          </section>
        )}

        <section className="ad-dsec">
          <h4>Reply from the shop</h4>
          <p className="ad-hint"><Icon n="info" size={14} />Shows under the review on the product page. Leave it empty and save to remove it.</p>
          <textarea className="ad-rev-reply" rows={3} maxLength={1000} value={reply}
            placeholder="e.g. Sorry about that - we've sent a replacement." onChange={(e) => setReply(e.target.value)} />
          <div className="ad-rev-reply-act">
            {r.reply && <small>Last reply by {r.replyBy || "the shop"}</small>}
            <button className="ad-btn ad-sm ad-primary" disabled={busy || reply.trim() === (r.reply || "")}
              onClick={() => call(`/admin/reviews/${r.id}/reply`, { text: reply }, reply.trim() ? "Reply saved" : "Reply removed")}>
              {reply.trim() || !r.reply ? "Save reply" : "Remove reply"}
            </button>
          </div>
        </section>
      </Drawer>

      {removing && (
        <Confirm danger title="Remove this photo?" confirmLabel="Remove it"
          text="It is deleted for good - shoppers will not see it and it cannot be brought back."
          onCancel={() => setRemoving(null)}
          onConfirm={() => { const m = removing; setRemoving(null); call(`/admin/reviews/media/${m.id}`, { action: "remove" }, "Photo removed"); }} />
      )}
    </>
  );
}

export function ReviewsSection({ flash }) {
  const [tab, setTab] = useState("pending");
  /* What is typed, and what has been asked for. Orders separates these too:
     without it every keystroke is a request, and on a slow connection the
     answers come back out of order. */
  const [term, setTerm] = useState("");
  const [q, setQ] = useState("");
  /* "" means do not care. Kept as strings so they travel as query params
     unchanged - "off" has to survive the trip, and `bool("0")` is true. */
  const [verified, setVerified] = useState("");
  const [photos, setPhotos] = useState("");
  const [open, setOpen] = useState(null);

  useEffect(() => {
    const id = setTimeout(() => setQ(term.trim()), 300);
    return () => clearTimeout(id);
  }, [term]);

  const path = useMemo(() => {
    const p = new URLSearchParams();
    if (tab !== "all") p.set("state", tab);
    if (q) p.set("q", q);
    if (verified) p.set("verified", verified);
    if (photos) p.set("photos", photos);
    const qs = p.toString();
    return "/admin/reviews" + (qs ? `?${qs}` : "");
  }, [tab, q, verified, photos]);

  /* Every 30 s, like the Odoo desk: a report can send a review back to
     Waiting while this screen is open. */
  const { data, loading, error, reload } = useResource(path, { pollMs: 30000, keepLast: true });

  const rows = data?.reviews || [];
  const counts = data?.counts || {};
  const report = data?.report;

  /* Read-after-write: which tab a review now belongs to is the server's. */
  const changed = async (ok) => {
    api.invalidate("/admin/reviews");
    await reload();
    if (ok) flash?.(ok);
  };

  const tile = (key, label, n, tone) => (
    <button type="button" className={"ad-rev-tile" + (tab === key ? " ad-on" : "") + (tone ? " " + tone : "")}
      aria-pressed={tab === key} onClick={() => setTab(key)}>
      <small>{label}</small><b>{n ?? 0}</b>
    </button>
  );

  return (
    <div className="ad-stack">
      <section className="ad-mini-stats ad-rev-tiles">
        <span><small>Average rating</small><b>{(data?.average ?? 0).toFixed(1)} ★</b></span>
        {tile("pending", "Waiting", counts.pending, "ad-warn")}
        {tile("published", "Published", counts.published)}
        {tile("hidden", "Hidden", counts.hidden, "ad-bad")}
      </section>

      {/* The same strip the Odoo desk shows: what to fix, not just what to read. */}
      {!!(report?.worst?.length || report?.complaints?.length) && (
        <section className="ad-card ad-rev-report">
          {!!report.worst?.length && (
            <p><b>Lowest rated</b>{report.worst.map((w) => `${w.product} ${Number(w.average).toFixed(1)}★ (${w.count})`).join(" · ")}</p>
          )}
          {!!report.complaints?.length && (
            <p><b>Top complaints (30 days)</b>{report.complaints.map((c) => `${c.tag} ${c.count}`).join(" · ")}</p>
          )}
        </section>
      )}

      <section className="ad-card">
        <div className="ad-toolbar">
          <Tabs value={tab} onChange={setTab} tabs={[["pending", "Waiting", counts.pending ?? 0], ["published", "Published", counts.published ?? 0], ["hidden", "Hidden", counts.hidden ?? 0], ["all", "All"]]} />
          <div className="ad-toolbar-right">
            <Search value={term} onChange={setTerm} placeholder="Product, customer or text" />
            <Select value={verified} onChange={setVerified} label="Bought it"
              options={[["", "Bought or not"], ["1", "Verified purchase"], ["0", "Not verified"]]} />
            <Select value={photos} onChange={setPhotos} label="Photos"
              options={[["", "With or without photos"], ["1", "With photos"], ["0", "Without photos"]]} />
          </div>
        </div>

        {error && !rows.length && (
          <Empty icon="info" title="We could not reach the shop" text={error.message}
            action="Try again" onAction={reload} />
        )}
        {loading && !rows.length && !error && (
          <Empty icon="star" title="Loading…" text="Fetching reviews." />
        )}

        {!!rows.length && (
          <ul className="ad-reviews">
            {rows.map((r, i) => (
              <li key={r.id} style={{ "--i": i }} className="ad-rev-row" onClick={() => setOpen(r)}>
                <Avatar name={r.by} size={38} tone={REVIEW_TONE(r.stars)} />
                <div className="ad-review-body">
                  <div className="ad-review-top">
                    <span className={"ad-stars ad-s" + r.stars}>{r.stars}★</span>
                    <b>{r.title || "No headline"}</b>
                    {r.verified && <span className="ad-pill ad-t-green">Verified</span>}
                    {!!r.photos && <small>📷 {r.photos}</small>}
                  </div>
                  <small className="ad-rev-who">{r.by} · {r.product} · {since(r.at)}</small>
                  <p>{r.text}</p>
                  <div className="ad-rev-chips">
                    {r.heldReason && r.state === "pending" && <span className="ad-pill ad-t-amber">Held: {r.heldReason}</span>}
                    {r.hiddenReason && r.state === "hidden" && <span className="ad-pill ad-t-grey">Hidden: {r.hiddenReason}</span>}
                    {!!r.mediaWaiting && <span className="ad-pill ad-t-amber">{r.mediaWaiting} photo{r.mediaWaiting === 1 ? "" : "s"} waiting</span>}
                    {!!r.reports && <span className="ad-pill ad-t-red">Reported ×{r.reports}</span>}
                    {r.reply && <span className="ad-pill ad-t-blue">Replied</span>}
                  </div>
                </div>
                <Icon n="right" size={16} />
              </li>
            ))}
          </ul>
        )}

        {!loading && !rows.length && !error && (
          <Empty icon="star" title="Nothing here"
            text={q || verified || photos
              ? "No review matches that. Try another tab, or clear a filter."
              : "No reviews in this tab."} />
        )}
      </section>

      {open && (
        <ReviewDrawer review={open} hideReasons={data?.hideReasons} onClose={() => setOpen(null)} onChanged={changed} />
      )}
    </div>
  );
}

/* =============================== settings ===============================
   Reads and saves the shop. Each tab is saved on its own, to the record that
   really decides it - the company, Odoo's payment providers, the shared
   settings record - so there is no second copy here to drift from them. What
   lives where is written down on the server, in mart369/models/settings_admin.py. */
/* The usual choices for "New for" and "Dormant after"; anything else is
   Custom, asked for in a small popup. A saved number that is not one of these
   is listed too, marked custom, so the box shows what is really set. */
const DAY_PRESETS = [15, 30, 45, 60, 90, 120, 150];

/* How long a customer has to answer a replacement (Settings > Orders), in
   minutes. */
const WAIT_PRESETS = {
  substituteQuick: [5, 10, 15, 20, 30],
  substituteExpress: [30, 60, 120, 240, 480, 1440],
};
const waitLabel = (m) => (m < 60 ? `${m} min` : `${Math.floor(m / 60)} h${m % 60 ? ` ${m % 60} min` : ""}`);

function DaysField({ label, value, onChange, prompt, presets = DAY_PRESETS, fmt = (d) => `${d} days`, unit = "days" }) {
  const [asking, setAsking] = useState(false);
  const days = presets.includes(value) || !value ? presets : [...presets, value].sort((a, b) => a - b);
  const options = [
    ...days.map((d) => [String(d), presets.includes(d) ? fmt(d) : `${fmt(d)} (custom)`]),
    ["custom", "Custom…"],
  ];
  return (
    /* A div, not a label: the popup is a portal, and React bubbles its clicks
       up here - a label would pass them on to the dropdown and reopen it. */
    <div className="ad-field">
      <span>{label}</span>
      <Select value={String(value)} options={options} label={label}
        onChange={(v) => (v === "custom" ? setAsking(true) : onChange(Number(v)))} />
      {asking && <DaysPrompt title={prompt} value={value} unit={unit} onCancel={() => setAsking(false)}
        onDone={(d) => { onChange(d); setAsking(false); }} />}
    </div>
  );
}

function DaysPrompt({ title, value, unit = "days", onCancel, onDone }) {
  const [text, setText] = useState(String(value || ""));
  const days = Number(text);
  const ok = Number.isInteger(days) && days >= 1 && days <= 43200;
  if (typeof document === "undefined") return null;
  return createPortal(
    <div className="ad-modal-wrap" onClick={onCancel}>
      <div className="ad-modal ad-days" role="dialog" aria-modal="true" aria-label={title} onClick={(e) => e.stopPropagation()}>
        <span className="ad-modal-ic"><Icon n="clock" size={22} /></span>
        <h3>{title}</h3>
        <label className="ad-field ad-days-in">
          <span className="ad-field-in">
            <input autoFocus inputMode="numeric" value={text} placeholder="e.g. 21" aria-label="Days"
              onChange={(e) => setText(e.target.value.replace(/\D/g, ""))}
              onKeyDown={(e) => { if (e.key === "Enter" && ok) onDone(days); if (e.key === "Escape") onCancel(); }} />
            <em>{unit}</em>
          </span>
        </label>
        <div>
          <button type="button" className="ad-btn" onClick={onCancel}>Cancel</button>
          <button type="button" className="ad-btn ad-primary" disabled={!ok} onClick={() => onDone(days)}>Use this</button>
        </div>
      </div>
    </div>,
    document.body
  );
}

function Field({ label, value, onChange, suffix, wide, type = "text", placeholder }) {
  return (
    <label className={"ad-field" + (wide ? " ad-span2" : "")}>
      <span>{label}</span>
      <span className="ad-field-in">
        <input type={type} value={value ?? ""} placeholder={placeholder} onChange={(e) => onChange(e.target.value)} />
        {suffix && <em>{suffix}</em>}
      </span>
    </label>
  );
}

const PAY_ICON = { cod: "cash", wallet: "wallet", gateway: "card" };
const PAY_STATE = { enabled: ["On", "green"], test: ["Test mode", "orange"], disabled: ["Off", "grey"] };

export function SettingsSection({ flash }) {
  const [tab, setTab] = useState("store");
  const { data, loading, error, reload } = useResource("/admin/settings");
  const saved = data?.settings;
  const [draft, setDraft] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  /* The draft is the saved copy until somebody types. Reset whenever the shop
     answers, so a save shows what was actually stored, not what was typed. */
  useEffect(() => { if (saved) setDraft(saved); }, [saved]);

  if (error && !saved) return <Empty icon="info" title="We could not reach the shop" text={error.message} action="Try again" onAction={reload} />;
  if (loading || !draft) return <Empty icon="gear" title="Loading…" text="Fetching settings." />;

  const group = tab === "payments" ? "pay" : tab;
  const dirty = JSON.stringify(draft[group]) !== JSON.stringify(saved[group]);
  const set = (g, key) => (v) => setDraft((d) => ({ ...d, [g]: { ...d[g], [key]: v } }));

  const save = async () => {
    setBusy(true); setErr("");
    let body = draft[group];
    if (group === "pay") {
      /* Only what the screen can change: the switches and the cash limit. */
      body = {
        providers: Object.fromEntries(draft.pay.providers.map((p) => [p.id, p.state !== "disabled"])),
        codLimit: draft.pay.codLimit,
      };
    }
    try {
      const res = await api(`/admin/settings/${group}`, { method: "POST", body });
      api.invalidate("/admin/settings");
      /* The checkout's own list of methods is cached too. */
      if (group === "pay") api.invalidate("/payment");
      setDraft(res.settings);
      await reload();
      flash?.("Settings saved");
    } catch (e) {
      setErr(e.message || "That did not save.");
    } finally {
      setBusy(false);
    }
  };

  const pay = draft.pay;
  const toggle = (id, on) => setDraft((d) => ({
    ...d, pay: { ...d.pay, providers: d.pay.providers.map((p) => (p.id === id ? { ...p, state: on ? "enabled" : "disabled" } : p)) },
  }));

  return (
    <div className="ad-stack">
      <section className="ad-card">
        <div className="ad-toolbar">
          <Tabs value={tab} onChange={(t) => { setTab(t); setErr(""); }} tabs={[["store", "Store"], ...(pay ? [["payments", "Payments"]] : []), ...(draft.customers ? [["customers", "Customers"]] : []), ...(draft.orders ? [["orders", "Orders"]] : []), ...(draft.reviews ? [["reviews", "Reviews"]] : []), ["alerts", "Alerts"]]} />
          <div className="ad-toolbar-right">
            {dirty && <span className="ad-dim">Unsaved changes</span>}
            <button className="ad-btn" disabled={!dirty || busy} onClick={() => { setDraft(saved); setErr(""); }}>Reset</button>
            <button className="ad-btn ad-primary" disabled={!dirty || busy} onClick={save}>{busy ? "Saving…" : "Save changes"}</button>
          </div>
        </div>
        {err && <p className="ad-hint ad-gap-note"><Icon n="info" size={14} /><span>{err}</span></p>}

        {tab === "store" && (
          <div className="ad-form ad-form-pad">
            <Field label="Store name" value={draft.store.name} onChange={set("store", "name")} wide />
            <Field label="Phone" value={draft.store.phone} onChange={set("store", "phone")} />
            <Field label="Email" value={draft.store.email} onChange={set("store", "email")} type="email" />
            <Field label="Address" value={draft.store.street} onChange={set("store", "street")} wide placeholder="Door number and street" />
            <Field label="Area" value={draft.store.street2} onChange={set("store", "street2")} />
            <Field label="City" value={draft.store.city} onChange={set("store", "city")} />
            <Field label="PIN code" value={draft.store.zip} onChange={set("store", "zip")} />
            <Field label="GSTIN" value={draft.store.gstin} onChange={set("store", "gstin")} />
            <p className="ad-hint ad-span2"><Icon n="info" size={14} />This is the company in Odoo — the same name and GSTIN print on invoices. When orders can be placed is set by the delivery slots, under Store › Delivery.</p>
          </div>
        )}

        {/* Delivery had a tab here, on invented numbers that saved nowhere.
           It is a live screen of its own now - Store > Delivery - and two
           screens claiming the same settings, one of them fiction, is worse
           than one. */}

        {tab === "payments" && pay && (
          <div className="ad-rows">
            {pay.providers.map((p, i) => {
              const [label, tone] = PAY_STATE[p.state] || PAY_STATE.disabled;
              const on = p.state !== "disabled";
              const locked = !on && !p.canEnable;
              return (
                <div key={p.id} className="ad-row-set" style={{ "--i": i }}>
                  <span className="ad-row-ic"><Icon n={PAY_ICON[p.kind] || "card"} size={18} /></span>
                  <span className="ad-row-txt">
                    <b>{p.name} <span className={"ad-pill ad-t-" + tone}><i />{label}</span></b>
                    <small>{p.kind === "cod" ? `Allowed up to ${money(pay.codLimit, pay.currency)}` : locked ? "Set up its keys in Odoo to switch it on" : p.kind === "wallet" ? "Balance, refunds and rewards" : "Card and UPI payments through this gateway"}</small>
                  </span>
                  {locked ? <span className="ad-dim">In Odoo</span> : <Switch on={on} onChange={(v) => toggle(p.id, v)} label={p.name} />}
                </div>
              );
            })}
            {pay.hasCod && (
              <div className="ad-row-set" style={{ "--i": pay.providers.length }}>
                <span className="ad-row-ic"><Icon n="shield" size={18} /></span>
                <span className="ad-row-txt"><b>Cash on delivery limit</b><small>Orders above this must be paid another way. 0 means no limit.</small></span>
                <span className="ad-field-in ad-narrow"><input value={pay.codLimit} inputMode="numeric" onChange={(e) => set("pay", "codLimit")(+e.target.value.replace(/[^\d.]/g, "") || 0)} aria-label="Cash on delivery limit" /><em>{pay.currency?.symbol || ""}</em></span>
              </div>
            )}
            <p className="ad-hint"><Icon n="info" size={14} />These are Odoo's payment providers — the checkout offers exactly what is switched on here.{pay.more ? ` ${pay.more} more are switched off and set up in Odoo.` : ""}</p>
          </div>
        )}

        {/* How long a customer is New, and when a quiet one turns Dormant.
            Saving updates every customer's badge at once. */}
        {tab === "customers" && draft.customers && (
          <div className="ad-form ad-form-pad">
            <DaysField label="New for" value={draft.customers.newDays}
              onChange={set("customers", "newDays")} prompt="New for how many days?" />
            <DaysField label="Dormant after, without a sign-in" value={draft.customers.dormantDays}
              onChange={set("customers", "dormantDays")} prompt="Dormant after how many days?" />
            <p className="ad-hint ad-span2"><Icon n="info" size={14} />A customer is New for this many days after signing up, then Active. Saving updates every customer's badge straight away.</p>
          </div>
        )}

        {/* How long a customer has to answer a replacement offer. */}
        {tab === "orders" && draft.orders && (
          <div className="ad-form ad-form-pad">
            <DaysField label="Quick orders: answer a replacement within" value={draft.orders.substituteQuick}
              presets={WAIT_PRESETS.substituteQuick} fmt={waitLabel} unit="min"
              onChange={set("orders", "substituteQuick")} prompt="Quick orders: how many minutes?" />
            <DaysField label="Express orders: answer a replacement within" value={draft.orders.substituteExpress}
              presets={WAIT_PRESETS.substituteExpress} fmt={waitLabel} unit="min"
              onChange={set("orders", "substituteExpress")} prompt="Express orders: how many minutes?" />
            <p className="ad-hint ad-span2"><Icon n="info" size={14} />When an item runs out and you offer a replacement, the customer has this long to accept it. No answer: the item is refunded to their 369 Wallet. A change applies to offers made from now on.</p>
          </div>
        )}

        {/* What a review may carry, and which words hold it for a look - the
            Odoo Settings screen's Reviews group (mart369_account config.py). */}
        {tab === "reviews" && draft.reviews && (
          <div className="ad-rows">
            {[["maxPhotos", "Photos per review", "How many photos a customer can add. 0 turns photos off.", ""],
              ["photoMb", "Largest photo", "Bigger photos are refused.", "MB"]].map(([k, t, d, unit], i) => (
              <div key={k} className="ad-row-set" style={{ "--i": i }}>
                <span className="ad-row-ic"><Icon n="camera" size={18} /></span>
                <span className="ad-row-txt"><b>{t}</b><small>{d}</small></span>
                <span className="ad-field-in ad-narrow"><input value={draft.reviews[k]} inputMode="numeric" aria-label={t}
                  onChange={(e) => set("reviews", k)(parseInt(e.target.value.replace(/D/g, ""), 10) || 0)} />{unit && <em>{unit}</em>}</span>
              </div>
            ))}
            <div className="ad-row-set" style={{ "--i": 2 }}>
              <span className="ad-row-ic"><Icon n="live" size={18} /></span>
              <span className="ad-row-txt"><b>Allow a video</b><small>One short clip per review, checked before it shows.</small></span>
              <Switch on={!!draft.reviews.video} onChange={set("reviews", "video")} label="Allow a video" />
            </div>
            {draft.reviews.video && [["videoSeconds", "Longest video", "Longer clips are refused.", "sec"], ["videoMb", "Largest video", "Bigger clips are refused.", "MB"]].map(([k, t, d, unit], i) => (
              <div key={k} className="ad-row-set" style={{ "--i": 3 + i }}>
                <span className="ad-row-ic"><Icon n="live" size={18} /></span>
                <span className="ad-row-txt"><b>{t}</b><small>{d}</small></span>
                <span className="ad-field-in ad-narrow"><input value={draft.reviews[k]} inputMode="numeric" aria-label={t}
                  onChange={(e) => set("reviews", k)(parseInt(e.target.value.replace(/D/g, ""), 10) || 0)} /><em>{unit}</em></span>
              </div>
            ))}
            <div className="ad-row-set ad-row-tall" style={{ "--i": 5 }}>
              <span className="ad-row-ic"><Icon n="shield" size={18} /></span>
              <span className="ad-row-txt"><b>Blocked words</b><small>A review with any of these waits in Waiting for someone to read it. One per line or comma-separated. Phone numbers and links are always held.</small>
                <textarea className="ad-rev-reply" rows={3} value={draft.reviews.blockedWords || ""} aria-label="Blocked words"
                  onChange={(e) => set("reviews", "blockedWords")(e.target.value)} placeholder="e.g. scam, fake" /></span>
            </div>
          </div>
        )}

        {tab === "alerts" && (
          <div className="ad-rows">
            {[["newOrder", "New orders", "Badge and bell when orders are waiting to be moved on"], ["lowStock", "Low stock", "Bell when products reach the level where the app says “Only N left”"]].map(([k, t, d], i) => (
              <div key={k} className="ad-row-set" style={{ "--i": i }}>
                <span className="ad-row-ic"><Icon n="bell" size={18} /></span>
                <span className="ad-row-txt"><b>{t}</b><small>{d}</small></span>
                <Switch on={!!draft.alerts[k]} onChange={set("alerts", k)} label={t} />
              </div>
            ))}
            <p className="ad-hint"><Icon n="info" size={14} />These are for this console. Email and SMS alerts are not set up.</p>
          </div>
        )}
      </section>
    </div>
  );
}
