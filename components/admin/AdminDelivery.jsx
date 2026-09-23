"use client";
/* ==========================================================================
   369 Mart admin — Delivery

   Three things decide what a delivery costs, when it can arrive, and whether
   we go there at all. Until now all three were editable only from the Odoo
   backend, so the people who actually run the shop could not touch any of
   them. They are one subject and one screen, three tabs deep:

     Fees          one rule per storefront — the four numbers the basket shows
     Slots         the chips the checkout offers, with their windows and caps
     Service areas which pincodes we reach, and how fast

   **Hours are stored as numbers, not as text.** 18.5 is half past six in the
   evening. The table prints "6:30 PM" beside the box so nobody has to hold
   that conversion in their head, but what gets typed and what gets sent is the
   number — the same number Odoo constrains to 0–24, so the server can refuse a
   25 without the screen having to invent its own rule about it.

   **A slot's key is not editable after it is made.** It is what the app calls
   the slot in its own state and what an order stores when somebody picks it;
   renaming it would orphan every order that already went out.

   Nothing here deletes. A fee rule, a slot and an area all get switched off
   instead, because an order placed against one still points at it.
   ========================================================================== */
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { money } from "@/lib/money";
import { useAction, useResource } from "@/lib/useFetch";
import { Confirm, Drawer, Empty, Icon, Pill, Switch, Tabs } from "./AdminUI";

/* The three shopper feeds this screen can change under a customer's feet. A
   staff edit that leaves them cached is an edit nobody sees. */
const SHOPPER_FEEDS = ["/cart/rules", "/slots", "/serviceability"];

const TABS = [
  ["fees", "Fees"],
  ["slots", "Slots"],
  ["areas", "Service areas"],
];

const ON_TONE = {
  on: { label: "On", tone: "green" },
  off: { label: "Off", tone: "grey" },
};

const BLANK_SLOT = {
  mode: "quick", kind: "window", key: "", top: "Today", sub: "", label: "",
  from_hour: 18, to_hour: 20, day_offset: 0, order_before: 24,
  fee: 0, capacity: 0, sequence: 10, active: true,
};

const BLANK_AREA = { pincode: "", name: "", quick: true, express: true, eta: "13 mins", active: true };

/* 18.5 -> "6:30 PM". The same arithmetic as `_mart369_clock` on the model,
   for the same reason it exists there: staff type a number, everyone else
   reads a time. Kept deliberately dumb — it never parses, only prints, so the
   two cannot drift over what a valid hour is. */
function clock(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return "";
  const hour = Math.floor(n) % 24;
  const minute = Math.round((n - Math.floor(n)) * 60);
  const suffix = hour < 12 ? "AM" : "PM";
  const shown = hour % 12 || 12;
  return minute ? `${shown}:${String(minute).padStart(2, "0")} ${suffix}` : `${shown} ${suffix}`;
}

/* An empty box means 0, not NaN. Typing over a number goes through "" on the
   way, and a NaN posted to the server comes back as an error about a field the
   operator is in the middle of filling in. */
const num = (v) => (v === "" || v === null || v === undefined ? 0 : Number(v));

/* ============================== small pieces ============================= */
function Field({ label, value, onChange, placeholder, suffix, wide, decimal }) {
  return (
    <label className={"ad-field" + (wide ? " ad-span2" : "")}>
      <span>{label}</span>
      <span className="ad-field-in">
        <input
          value={value ?? ""}
          inputMode={decimal ? "decimal" : undefined}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder} />
        {suffix && <em>{suffix}</em>}
      </span>
    </label>
  );
}

/* =============================== fees tab =============================== */
/* One panel per storefront. Saved on its own: the two rules are separate
   records and somebody changing the Express fee has no business also writing
   whatever is half-typed in the Quick panel. */
function RuleCard({ rule, busy, currency, onSave }) {
  const [form, setForm] = useState(() => ({
    label: rule.label, eta: rule.eta, min_order: rule.minOrder,
    free_above: rule.freeAbove, fee: rule.fee, active: rule.active,
  }));
  const [error, setError] = useState("");
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  /* The screen polls. Without this a tick landing while somebody is typing
     would leave the boxes showing the server's older numbers. */
  useEffect(() => {
    setForm({
      label: rule.label, eta: rule.eta, min_order: rule.minOrder,
      free_above: rule.freeAbove, fee: rule.fee, active: rule.active,
    });
  }, [rule.id, rule.label, rule.eta, rule.minOrder, rule.freeAbove, rule.fee, rule.active]);

  const dirty = form.label !== rule.label || form.eta !== rule.eta
    || num(form.min_order) !== rule.minOrder || num(form.free_above) !== rule.freeAbove
    || num(form.fee) !== rule.fee || form.active !== rule.active;

  const save = async () => {
    setError("");
    const message = await onSave(rule.id, {
      label: form.label, eta: form.eta, active: form.active,
      min_order: num(form.min_order), free_above: num(form.free_above), fee: num(form.fee),
    });
    if (message) setError(message);
  };

  return (
    <section className="ad-dsec ad-rule">
      <h4>
        {rule.modeLabel}
        <em>{rule.mode}</em>
        <span className="ad-rule-on">
          <Switch on={form.active} onChange={(v) => set("active", v)}
            label={`${rule.modeLabel} delivery on`} />
        </span>
      </h4>

      {error && <p className="ad-form-error" role="alert">{error}</p>}

      <div className="ad-form">
        <Field label="Shown as" value={form.label} onChange={(v) => set("label", v)}
          placeholder="Quick" />
        <Field label="Delivery promise" value={form.eta} onChange={(v) => set("eta", v)}
          placeholder="Delivery in 13 mins" />
        <Field label="Minimum order" value={form.min_order} decimal
          onChange={(v) => set("min_order", v)} placeholder="0" />
        <Field label="Free delivery above" value={form.free_above} decimal
          onChange={(v) => set("free_above", v)} placeholder="0" />
        <Field label="Delivery fee" value={form.fee} decimal
          onChange={(v) => set("fee", v)} placeholder="0" />
      </div>

      <p className="ad-hint" role="note">
        <Icon n="info" size={14} />
        {num(form.free_above) > 0
          ? `Under ${money(num(form.free_above), currency)} the basket is charged ${money(num(form.fee), currency)} — above it, nothing.`
          : `Delivery is never free here: every ${rule.modeLabel.toLowerCase()} basket is charged ${money(num(form.fee), currency)}, whatever it comes to.`}
        {num(form.min_order) > 0 ? ` Below ${money(num(form.min_order), currency)} the customer cannot pay at all.` : ""}
      </p>

      <div className="ad-rule-foot">
        <button className="ad-btn ad-primary" disabled={busy || !dirty} onClick={save}>
          Save {rule.modeLabel}
        </button>
      </div>
    </section>
  );
}

/* =============================== slot form =============================== */
function SlotDrawer({ slot, modes, kinds, onClose, onSaved }) {
  const act = useAction();
  const [form, setForm] = useState(() => (slot
    ? {
      mode: slot.mode, kind: slot.kind, key: slot.key, top: slot.top, sub: slot.sub,
      label: slot.label, from_hour: slot.fromHour, to_hour: slot.toHour,
      day_offset: slot.dayOffset, order_before: slot.orderBefore,
      fee: slot.fee, capacity: slot.capacity, sequence: slot.sequence, active: slot.active,
    }
    : { ...BLANK_SLOT }));
  const [error, setError] = useState("");
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  const isWindow = form.kind === "window";

  const save = async () => {
    setError("");
    const body = {
      mode: form.mode, kind: form.kind, top: form.top, sub: form.sub, label: form.label,
      from_hour: num(form.from_hour), to_hour: num(form.to_hour),
      day_offset: num(form.day_offset), order_before: num(form.order_before),
      fee: num(form.fee), capacity: num(form.capacity), sequence: num(form.sequence),
      active: form.active,
    };
    /* The key identifies the slot to the app and to every order that booked
       one, so it is set once and never rewritten. */
    if (!slot) body.key = (form.key || "").trim();

    const done = await act.run(async () => {
      await api(slot ? `/admin/delivery/slots/${slot.id}` : "/admin/delivery/slots",
        { method: slot ? "PATCH" : "POST", body });
      return true;
    });
    if (done === null) {
      /* The drawer stays open with the message in it: closing it would throw
         away everything just typed. */
      setError(act.error?.message || "That could not be saved.");
      return;
    }
    onSaved(slot ? "Slot updated" : "Slot added");
  };

  return (
    <Drawer wide onClose={onClose}
      title={slot ? `Edit ${slot.top}` : "New slot"}
      sub={slot ? `${slot.modeLabel} · ${slot.key}` : "A chip on the checkout's slot step"}
      foot={(close) => (
        <>
          <button className="ad-btn" onClick={close}>Cancel</button>
          <button className="ad-btn ad-primary" disabled={act.busy} onClick={save}>
            {slot ? "Save" : "Add it"}<Icon n="right" size={15} />
          </button>
        </>
      )}>

      {error && <p className="ad-form-error" role="alert">{error}</p>}

      <section className="ad-dsec">
        <h4>What the chip says</h4>
        <div className="ad-form">
          <Field label="Heading" value={form.top} onChange={(v) => set("top", v)}
            placeholder="Today" />
          <Field label="Detail" value={form.sub} onChange={(v) => set("sub", v)}
            placeholder={isWindow ? `${clock(num(form.from_hour))} - ${clock(num(form.to_hour))}` : "10–20 min"} />
          <Field label="Confirmation line" value={form.label} wide
            onChange={(v) => set("label", v)}
            placeholder="Left empty, the shop writes it from the heading and the window" />
        </div>
      </section>

      <section className="ad-dsec">
        <h4>Which storefront, and what kind</h4>
        <div className="ad-form">
          <div className="ad-field">
            <span>Storefront</span>
            <ChoiceRow value={form.mode} onChange={(v) => set("mode", v)} options={modes} />
          </div>
          <div className="ad-field">
            <span>Kind</span>
            <ChoiceRow value={form.kind} onChange={(v) => set("kind", v)} options={kinds} />
          </div>
          {!slot && (
            <Field label="Key" value={form.key} onChange={(v) => set("key", v)}
              placeholder="eve" />
          )}
          <Field label="Order in the list" value={form.sequence}
            onChange={(v) => set("sequence", v)} placeholder="10" />
        </div>
        {!slot && (
          <p className="ad-hint">
            <Icon n="info" size={14} />
            The key is how the app and every order refer to this slot. Pick a short
            one — now, eve, tm, std — and it cannot be changed afterwards.
          </p>
        )}
      </section>

      <section className="ad-dsec">
        <h4>When it runs</h4>
        <div className="ad-form">
          {isWindow && (
            <>
              <Field label="From" value={form.from_hour} decimal suffix={clock(num(form.from_hour))}
                onChange={(v) => set("from_hour", v)} placeholder="18" />
              <Field label="To" value={form.to_hour} decimal suffix={clock(num(form.to_hour))}
                onChange={(v) => set("to_hour", v)} placeholder="20" />
            </>
          )}
          <Field label="Days ahead" value={form.day_offset}
            onChange={(v) => set("day_offset", v)} placeholder="0" />
          <Field label="Stop offering after" value={form.order_before} decimal
            suffix={num(form.order_before) >= 24 ? "never" : clock(num(form.order_before))}
            onChange={(v) => set("order_before", v)} placeholder="24" />
        </div>
        <p className="ad-hint">
          <Icon n="info" size={14} />
          Hours are numbers: 18.5 is 6:30 PM. 0 is today and 1 is tomorrow.
          Leave the cut-off at 24 and the slot is always offered.
        </p>
      </section>

      <section className="ad-dsec">
        <h4>What it costs, and how many it takes</h4>
        <div className="ad-form">
          <Field label="Extra fee" value={form.fee} decimal
            onChange={(v) => set("fee", v)} placeholder="0" />
          <Field label="Orders per slot" value={form.capacity}
            onChange={(v) => set("capacity", v)} placeholder="0" />
        </div>
        <p className="ad-hint">
          <Icon n="info" size={14} />
          0 orders means no limit. Once a window is full the app stops offering it
          for that day on its own.
        </p>
      </section>
    </Drawer>
  );
}

/* A row of buttons rather than a dropdown: there are two or three options and
   both matter enough to be read without opening anything. */
function ChoiceRow({ value, onChange, options }) {
  return (
    <div className="ad-choice" role="radiogroup">
      {(options || []).map((o) => (
        <button key={o.key} type="button" role="radio" aria-checked={value === o.key}
          className={value === o.key ? "ad-on" : ""} onClick={() => onChange(o.key)}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

/* =============================== area form =============================== */
function AreaDrawer({ area, onClose, onSaved }) {
  const act = useAction();
  const [form, setForm] = useState(() => (area
    ? { pincode: area.pincode, name: area.name, quick: area.quick, express: area.express, eta: area.eta, active: area.active }
    : { ...BLANK_AREA }));
  const [error, setError] = useState("");
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const save = async () => {
    setError("");
    const body = {
      pincode: (form.pincode || "").trim(), name: form.name, eta: form.eta,
      quick: !!form.quick, express: !!form.express, active: !!form.active,
    };
    const done = await act.run(async () => {
      await api(area ? `/admin/delivery/areas/${area.id}` : "/admin/delivery/areas",
        { method: area ? "PATCH" : "POST", body });
      return true;
    });
    if (done === null) {
      setError(act.error?.message || "That could not be saved.");
      return;
    }
    onSaved(area ? "Area updated" : "Area added");
  };

  return (
    <Drawer onClose={onClose}
      title={area ? `Edit ${area.pincode}` : "New service area"}
      sub={area ? area.name || "No name" : "A pincode, or the start of one"}
      foot={(close) => (
        <>
          <button className="ad-btn" onClick={close}>Cancel</button>
          <button className="ad-btn ad-primary" disabled={act.busy} onClick={save}>
            {area ? "Save" : "Add it"}<Icon n="right" size={15} />
          </button>
        </>
      )}>

      {error && <p className="ad-form-error" role="alert">{error}</p>}

      <section className="ad-dsec">
        <h4>Where</h4>
        <div className="ad-form">
          <Field label="Pincode" value={form.pincode} onChange={(v) => set("pincode", v)}
            placeholder="682016" />
          <Field label="Area" value={form.name} onChange={(v) => set("name", v)}
            placeholder="Kochi" />
        </div>
        <p className="ad-hint">
          <Icon n="info" size={14} />
          A full pincode, or the start of one: 68 covers every pincode beginning
          with it. The most specific entry wins, so 6820 beats 68. The area name
          is for you — customers never see it.
        </p>
      </section>

      <section className="ad-dsec">
        <h4>What reaches it</h4>
        <div className="ad-kv-rows">
          <label className="ad-kv-row">
            <span>Quick delivery<small>The 10-minute grocery run</small></span>
            <Switch on={!!form.quick} onChange={(v) => set("quick", v)} label="Quick delivery" />
          </label>
          <label className="ad-kv-row">
            <span>Express delivery<small>Items that ship over days</small></span>
            <Switch on={!!form.express} onChange={(v) => set("express", v)} label="Express delivery" />
          </label>
        </div>
        <Field label="Delivery promise" value={form.eta} onChange={(v) => set("eta", v)}
          placeholder="13 mins" />
        <p className="ad-hint">
          <Icon n="info" size={14} />
          Switch both off and the pincode is told we do not deliver there yet.
        </p>
      </section>
    </Drawer>
  );
}

/* ================================ the page ============================== */
export function DeliverySection({ flash }) {
  const [tab, setTab] = useState("fees");
  const [slotEdit, setSlotEdit] = useState(null); // a slot, or {} for a new one
  const [areaEdit, setAreaEdit] = useState(null);
  const [drop, setDrop] = useState(null); // {kind, row}

  const { data, loading, error, reload } = useResource("/admin/delivery",
    { pollMs: 60000, keepLast: true });
  const act = useAction();

  const rules = data?.rules || [];
  /* Which money these amounts are in, travelling with them - the house rule
     for every console screen that prints a price. */
  const currency = data?.currency;
  const slots = data?.slots || [];
  const areas = data?.areas || [];
  const modes = data?.modes || [];
  const kinds = data?.kinds || [];

  const counts = useMemo(() => ({
    fees: rules.filter((r) => r.active).length,
    slots: slots.filter((s) => s.active).length,
    areas: areas.filter((a) => a.active).length,
  }), [rules, slots, areas]);

  /* Read-after-write, like every live section. Two caches have to be dropped,
     not one: the console's own list, and whichever shopper feed this edit
     changed — a fee the customer's basket has already cached is a fee the edit
     did not reach. */
  const refresh = () => {
    api.invalidate("/admin/delivery");
    SHOPPER_FEEDS.forEach((feed) => api.invalidate(feed));
  };

  const run = (fn, ok) =>
    act.run(async () => {
      await fn();
      refresh();
      await reload();
      if (ok) flash?.(ok);
      return true;
    }).then((r) => {
      if (r === null) flash?.(act.error?.message || "That did not work.", "bad");
      return r;
    });

  /* The fee panels keep their own error, under the panel the server named,
     rather than flashing it away over a form somebody is still in. */
  const saveRule = async (id, body) => {
    const done = await act.run(async () => {
      await api(`/admin/delivery/rules/${id}`, { method: "PATCH", body });
      return true;
    });
    if (done === null) return act.error?.message || "That could not be saved.";
    refresh();
    await reload();
    flash?.("Delivery fees saved");
    return "";
  };

  const retireSlot = (slot, retired) =>
    run(() => api(`/admin/delivery/slots/${slot.id}`, { method: "PATCH", body: { active: !retired } }),
      retired ? "Slot switched off" : "Slot back on");

  const retireArea = (area, retired) =>
    run(() => api(`/admin/delivery/areas/${area.id}`, { method: "PATCH", body: { active: !retired } }),
      retired ? "Area switched off" : "Area back on");

  const saved = (setter) => async (msg) => {
    setter(null);
    refresh();
    await reload();
    flash?.(msg);
  };

  const errorState = error && (
    <Empty icon="info" title="We could not reach the shop"
      text={error.message} action="Try again" onAction={reload} />
  );
  const loadingState = loading && !data && !error && (
    <Empty icon="box" title="Loading…" text="Fetching delivery settings." />
  );

  return (
    <div className="ad-stack">
      <section className="ad-mini-stats">
        <span><small>Storefronts</small><b>{counts.fees}</b></span>
        <span><small>Slots offered</small><b>{counts.slots}</b></span>
        <span><small>Areas covered</small><b>{counts.areas}</b></span>
        <span className={areas.length && !counts.areas ? "ad-bad" : ""}>
          <small>Switched off</small>
          <b>{(slots.length - counts.slots) + (areas.length - counts.areas)}</b>
        </span>
      </section>

      <section className="ad-card">
        <div className="ad-toolbar">
          <Tabs value={tab} onChange={setTab}
            tabs={TABS.map(([k, label]) => [k, label, counts[k] ?? null])} />
          <div className="ad-toolbar-right">
            {tab === "slots" && (
              <button className="ad-btn ad-primary" onClick={() => setSlotEdit({})}>
                <Icon n="plus" size={16} />New slot
              </button>
            )}
            {tab === "areas" && (
              <button className="ad-btn ad-primary" onClick={() => setAreaEdit({})}>
                <Icon n="plus" size={16} />New area
              </button>
            )}
          </div>
        </div>

        {errorState}
        {loadingState}

        {/* ------------------------------------------------------- fees */}
        {tab === "fees" && !error && !!rules.length && (
          <div className="ad-rules">
            {rules.map((r, i) => (
              <div key={r.id} style={{ "--i": i }}>
                <RuleCard rule={r} busy={act.busy} currency={currency} onSave={saveRule} />
              </div>
            ))}
          </div>
        )}
        {tab === "fees" && !loading && !rules.length && !error && (
          <Empty icon="box" title="No delivery rules"
            text="Neither storefront has a rule, so the basket has no fee to show. They are seeded with the module — reinstall it, or add them in Odoo." />
        )}

        {/* ------------------------------------------------------ slots */}
        {tab === "slots" && !error && !!slots.length && (
          <div className="ad-table-wrap">
            <table className="ad-table">
              <thead>
                <tr>
                  <th>Chip</th><th>Storefront</th><th>Kind</th><th>When</th>
                  <th className="ad-num">Fee</th><th className="ad-num">Cap</th>
                  <th>State</th><th />
                </tr>
              </thead>
              <tbody>
                {slots.map((s, i) => (
                  <tr key={s.id} style={{ "--i": i }} className={s.active ? "" : "ad-row-warn"}>
                    <td>
                      <b>{s.top}</b>
                      <small className="ad-sub">{s.sub || "—"} · {s.key}</small>
                    </td>
                    <td>{s.modeLabel}</td>
                    <td>{s.kindLabel}</td>
                    <td>
                      {s.kind === "window" ? `${clock(s.fromHour)} – ${clock(s.toHour)}` : "—"}
                      <small className="ad-sub">
                        {s.dayOffset === 0 ? "Today" : s.dayOffset === 1 ? "Tomorrow" : `In ${s.dayOffset} days`}
                        {s.orderBefore < 24 ? ` · until ${clock(s.orderBefore)}` : ""}
                      </small>
                    </td>
                    <td className="ad-num">{s.fee ? money(s.fee, currency) : "Free"}</td>
                    <td className="ad-num">{s.capacity || "∞"}</td>
                    <td><Pill s={s.active ? "on" : "off"} map={ON_TONE} /></td>
                    <td className="ad-row-act">
                      <button className="ad-btn ad-sm" disabled={act.busy}
                        onClick={() => setSlotEdit(s)}>Edit</button>
                      {s.active
                        ? <button className="ad-btn ad-sm" disabled={act.busy}
                          onClick={() => setDrop({ kind: "slot", row: s })}>Switch off</button>
                        : <button className="ad-btn ad-sm" disabled={act.busy}
                          onClick={() => retireSlot(s, false)}>Put back</button>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {tab === "slots" && !loading && !slots.length && !error && (
          <Empty icon="clock" title="No slots"
            text="The checkout has no window to offer. Add one and it appears on the slot step." />
        )}

        {/* ------------------------------------------------------ areas */}
        {tab === "areas" && !error && !!areas.length && (
          <div className="ad-table-wrap">
            <table className="ad-table">
              <thead>
                <tr>
                  <th>Pincode</th><th>Area</th><th>Quick</th><th>Express</th>
                  <th>Promise</th><th>State</th><th />
                </tr>
              </thead>
              <tbody>
                {areas.map((a, i) => (
                  <tr key={a.id} style={{ "--i": i }} className={a.active ? "" : "ad-row-warn"}>
                    <td><b>{a.pincode}</b>
                      {a.pincode.length < 6 && <small className="ad-sub">and everything under it</small>}
                    </td>
                    <td>{a.name || <span className="ad-sub">—</span>}</td>
                    <td><Pill s={a.quick ? "on" : "off"} map={ON_TONE} /></td>
                    <td><Pill s={a.express ? "on" : "off"} map={ON_TONE} /></td>
                    <td>{a.eta || "—"}</td>
                    <td><Pill s={a.active ? "on" : "off"} map={ON_TONE} /></td>
                    <td className="ad-row-act">
                      <button className="ad-btn ad-sm" disabled={act.busy}
                        onClick={() => setAreaEdit(a)}>Edit</button>
                      {a.active
                        ? <button className="ad-btn ad-sm" disabled={act.busy}
                          onClick={() => setDrop({ kind: "area", row: a })}>Switch off</button>
                        : <button className="ad-btn ad-sm" disabled={act.busy}
                          onClick={() => retireArea(a, false)}>Put back</button>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {tab === "areas" && !loading && !areas.length && !error && (
          <Empty icon="pin" title="Nowhere is covered"
            text="With no area on the list every pincode is told we do not deliver there. Add the ones you reach." />
        )}
      </section>

      {slotEdit && (
        <SlotDrawer slot={slotEdit.id ? slotEdit : null} modes={modes} kinds={kinds}
          onClose={() => setSlotEdit(null)} onSaved={saved(setSlotEdit)} />
      )}

      {areaEdit && (
        <AreaDrawer area={areaEdit.id ? areaEdit : null}
          onClose={() => setAreaEdit(null)} onSaved={saved(setAreaEdit)} />
      )}

      {drop && (
        <Confirm danger confirmLabel="Switch it off"
          title={drop.kind === "slot" ? "Switch this slot off?" : "Stop delivering here?"}
          text={drop.kind === "slot"
            ? `“${drop.row.top}” stops being offered at checkout. Orders already booked into it keep their slot — this only closes it to new ones.`
            : `Customers in ${drop.row.pincode} will be told we do not deliver there yet. Orders already placed are unaffected.`}
          onCancel={() => setDrop(null)}
          onConfirm={() => {
            const { kind, row } = drop;
            setDrop(null);
            if (kind === "slot") retireSlot(row, true); else retireArea(row, true);
          }} />
      )}
    </div>
  );
}
