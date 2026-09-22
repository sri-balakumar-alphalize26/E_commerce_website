"use client";
/* ==========================================================================
   369 Mart admin — Offers · Reviews · Settings
   ========================================================================== */
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { money } from "@/lib/money";
import { useAction, useResource } from "@/lib/useFetch";
import { Avatar, Confirm, Drawer, Empty, Icon, Search, Select, Switch, Tabs } from "./AdminUI";
import { since } from "./format";
import { inr } from "./adminData";

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
          <input value={f.title} onChange={set("title")} placeholder="25% off staples" /></label>
        <label className="ad-field ad-span2"><span>Small print</span>
          <input value={f.note} onChange={set("note")} placeholder="Atta, rice and oils" /></label>

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
   Moderation, read and written in the shop.

   Every review is published the moment it is written, and Waiting is a list
   to read afterwards rather than a gate to pass - a product page that waits
   for somebody to work a queue goes quiet the first week nobody does.

   Staff decide whether a review is shown. They never edit one: the server's
   allow-list takes `state` and nothing else, so there is no control here for
   the stars, the headline or the words. */
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
  const [drop, setDrop] = useState(null);

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

  /* No `deps`: useResource already keys its fetch on `path`. */
  const { data, loading, error, reload } = useResource(path);
  const act = useAction();

  const rows = data?.reviews || [];
  const counts = data?.counts || {};

  /* Read-after-write. The tile numbers and which tab a review now belongs to
     are both the server's, and a row patched locally would sit in a tab it no
     longer matches until the next reload. */
  const run = (fn, ok) =>
    act.run(async () => {
      await fn();
      api.invalidate("/admin/reviews");
      await reload();
      if (ok) flash?.(ok);
      return true;
    }).then((r) => {
      if (r === null) flash?.(act.error?.message || "That did not work.", "bad");
      return r;
    });

  const setState = (r, state, ok) =>
    run(() => api(`/admin/reviews/${r.id}`, { method: "PATCH", body: { state } }), ok);

  return (
    <div className="ad-stack">
      <section className="ad-mini-stats">
        <span><small>Average rating</small><b>{(data?.average ?? 0).toFixed(1)} ★</b></span>
        <span className="ad-warn"><small>Waiting</small><b>{counts.pending ?? 0}</b></span>
        <span><small>Published</small><b>{counts.published ?? 0}</b></span>
        <span className="ad-bad"><small>Hidden</small><b>{counts.hidden ?? 0}</b></span>
      </section>

      <section className="ad-card">
        <div className="ad-toolbar">
          <Tabs value={tab} onChange={setTab} tabs={[["pending", "Waiting", counts.pending ?? 0], ["published", "Published", counts.published ?? 0], ["hidden", "Hidden", counts.hidden ?? 0], ["all", "All"]]} />
          <div className="ad-toolbar-right">
            <Search value={term} onChange={setTerm} placeholder="Product, customer or text" />
            {/* The two the Odoo search view has always had and this never did. */}
            <Select value={verified} onChange={setVerified} label="Bought it"
              options={[["", "Bought or not"], ["1", "Verified purchase"], ["0", "Not verified"]]} />
            <Select value={photos} onChange={setPhotos} label="Photos"
              options={[["", "With or without photos"], ["1", "With photos"], ["0", "Without photos"]]} />
          </div>
        </div>

        {error && (
          <Empty icon="info" title="We could not reach the shop" text={error.message}
            action="Try again" onAction={reload} />
        )}
        {loading && !rows.length && !error && (
          <Empty icon="star" title="Loading…" text="Fetching reviews." />
        )}

        {!error && !!rows.length && (
          <ul className="ad-reviews">
            {rows.map((r, i) => (
              <li key={r.id} style={{ "--i": i }}>
                <Avatar name={r.by} size={38} tone={r.stars >= 4 ? "ad-a-green" : r.stars >= 3 ? "ad-a-orange" : "ad-a-red"} />
                <div className="ad-review-body">
                  <div className="ad-review-top">
                    <span className={"ad-stars ad-s" + r.stars}>{r.stars}★</span>
                    <b>{r.title || "No headline"}</b>
                    <small>{r.by} · {r.product} · {since(r.at)}</small>
                  </div>
                  <p>{r.text}</p>
                </div>
                <div className="ad-review-act">
                  {r.state !== "published" && (
                    <button className="ad-btn ad-sm ad-primary" disabled={act.busy}
                      onClick={() => setState(r, "published", "Review published")}>Publish</button>
                  )}
                  {r.state !== "hidden" && (
                    <button className="ad-btn ad-sm" disabled={act.busy}
                      onClick={() => setDrop(r)}>Hide</button>
                  )}
                </div>
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

      {drop && (
        <Confirm danger title="Hide this review?" confirmLabel="Hide review"
          text={`“${drop.title || "This review"}” by ${drop.by} will no longer show on the product page, and will stop counting towards its rating.`}
          onCancel={() => setDrop(null)}
          onConfirm={() => { const r = drop; setDrop(null); setState(r, "hidden", "Review hidden"); }} />
      )}
    </div>
  );
}

/* =============================== settings =============================== */
function Field({ label, value, onChange, suffix, wide, type = "text" }) {
  return (
    <label className={"ad-field" + (wide ? " ad-span2" : "")}>
      <span>{label}</span>
      <span className="ad-field-in">
        <input type={type} value={value} onChange={(e) => onChange(e.target.value)} />
        {suffix && <em>{suffix}</em>}
      </span>
    </label>
  );
}

export function SettingsSection({ settings, setSettings, flash }) {
  const [s, setS] = useState(settings);
  const [tab, setTab] = useState("store");
  const dirty = JSON.stringify(s) !== JSON.stringify(settings);
  const set = (group, key) => (v) => setS({ ...s, [group]: { ...s[group], [key]: v } });
  const save = () => { setSettings(s); flash("Settings saved"); };

  return (
    <div className="ad-stack">
      <section className="ad-card">
        <div className="ad-toolbar">
          <Tabs value={tab} onChange={setTab} tabs={[["store", "Store"], ["delivery", "Delivery"], ["payments", "Payments"], ["alerts", "Alerts"]]} />
          <div className="ad-toolbar-right">
            {dirty && <span className="ad-dim">Unsaved changes</span>}
            <button className="ad-btn" disabled={!dirty} onClick={() => setS(settings)}>Reset</button>
            <button className="ad-btn ad-primary" disabled={!dirty} onClick={save}>Save changes</button>
          </div>
        </div>

        {tab === "store" && (
          <div className="ad-form ad-form-pad">
            <Field label="Store name" value={s.store.name} onChange={set("store", "name")} wide />
            <Field label="Phone" value={s.store.phone} onChange={set("store", "phone")} />
            <Field label="Email" value={s.store.email} onChange={set("store", "email")} />
            <Field label="Address" value={s.store.address} onChange={set("store", "address")} wide />
            <Field label="GSTIN" value={s.store.gstin} onChange={set("store", "gstin")} />
            <div className="ad-field-row">
              <Field label="Opens" type="time" value={s.store.open} onChange={set("store", "open")} />
              <Field label="Closes" type="time" value={s.store.close} onChange={set("store", "close")} />
            </div>
          </div>
        )}

        {tab === "delivery" && (
          <div className="ad-two">
            {[["quick", "Quick", "Groceries in 10–20 minutes"], ["express", "Express", "Electronics and home in 2–5 days"]].map(([k, title, sub]) => (
              <div key={k} className="ad-panel">
                <h3>{title}<small>{sub}</small></h3>
                <div className="ad-form">
                  <Field label="Minimum order" value={s[k].min} onChange={(v) => set(k, "min")(+v.replace(/\D/g, "") || 0)} suffix="₹" />
                  <Field label="Delivery fee" value={s[k].fee} onChange={(v) => set(k, "fee")(+v.replace(/\D/g, "") || 0)} suffix="₹" />
                  <Field label="Free above" value={s[k].freeAbove} onChange={(v) => set(k, "freeAbove")(+v.replace(/\D/g, "") || 0)} suffix="₹" />
                  <Field label={k === "quick" ? "Delivery radius" : "Slots per day"} value={k === "quick" ? s[k].radius : s[k].slots} onChange={(v) => set(k, k === "quick" ? "radius" : "slots")(+v.replace(/\D/g, "") || 0)} suffix={k === "quick" ? "km" : "slots"} />
                  <Field label="Promised time" value={s[k].eta} onChange={set(k, "eta")} wide />
                </div>
              </div>
            ))}
          </div>
        )}

        {tab === "payments" && (
          <div className="ad-rows">
            {[["upi", "UPI", "Google Pay, PhonePe, Paytm, any UPI ID"], ["card", "Cards", "Visa, Mastercard, RuPay, Amex"], ["netbanking", "Net banking", "All major Indian banks"], ["cod", "Cash on delivery", `Allowed up to ${inr(s.pay.codLimit)}`], ["wallet", "369 Wallet", "Balance, refunds and cashback"]].map(([k, t, d], i) => (
              <div key={k} className="ad-row-set" style={{ "--i": i }}>
                <span className="ad-row-ic"><Icon n={k === "upi" ? "upi" : k === "card" ? "card" : k === "netbanking" ? "bank" : k === "cod" ? "cash" : "wallet"} size={18} /></span>
                <span className="ad-row-txt"><b>{t}</b><small>{d}</small></span>
                <Switch on={s.pay[k]} onChange={set("pay", k)} label={t} />
              </div>
            ))}
            <div className="ad-row-set" style={{ "--i": 5 }}>
              <span className="ad-row-ic"><Icon n="shield" size={18} /></span>
              <span className="ad-row-txt"><b>Cash on delivery limit</b><small>Orders above this must be paid online</small></span>
              <span className="ad-field-in ad-narrow"><input value={s.pay.codLimit} onChange={(e) => set("pay", "codLimit")(+e.target.value.replace(/\D/g, "") || 0)} aria-label="COD limit" /><em>₹</em></span>
            </div>
          </div>
        )}

        {tab === "alerts" && (
          <div className="ad-rows">
            {[["newOrder", "New order", "Beep and badge when an order comes in"], ["lowStock", "Low stock", "When a product reaches its reorder level"], ["cancelled", "Cancellations", "When a customer cancels an order"], ["dailySummary", "Daily summary", "Sales and stock email at closing time"]].map(([k, t, d], i) => (
              <div key={k} className="ad-row-set" style={{ "--i": i }}>
                <span className="ad-row-ic"><Icon n="bell" size={18} /></span>
                <span className="ad-row-txt"><b>{t}</b><small>{d}</small></span>
                <Switch on={s.alerts[k]} onChange={set("alerts", k)} label={t} />
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
