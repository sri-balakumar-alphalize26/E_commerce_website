"use client";
/* ==========================================================================
   369 Mart — Delivery address form (Checkout and Account → Delivery Address)
   Home / Work / Other, a country, then every line a rider reads off the
   parcel, each in its own box. Like Amazon, the country decides the rest:
   the phone prefix, the states and the pincode length all come from the shop
   (/addresses/form?country=), never from this file. For India, typing a full
   pincode asks the shop for its city, state and post-office areas and fills
   in whatever the shopper has not typed themselves.
   ========================================================================== */
import { useEffect, useMemo, useRef, useState } from "react";
import Pick from "./Pick";
import { api } from "@/lib/api";
import { nationalNumber } from "@/lib/address";

const LABELS = ["Home", "Work", "Other"];

/* The account's own mobile, as digits for this form - but only when it is a
   number of the country being filled in. An Omani account number is no use
   in front of +91, and the prefix is not known until the shop has said. */
function ownNumber(phone, dial) {
  const p = String(phone || "");
  if (!p || !dial || (p.startsWith("+") && !p.startsWith(dial))) return "";
  return nationalNumber(p, dial);
}

/* A saved address (or a location-picker prefill) as the form's fields. */
function draftFrom(a = {}, me, dial) {
  return {
    label: LABELS.includes(a.label) ? a.label : a.id ? "Other" : "Home",
    name: a.id ? a.name || "" : a.name || me?.name || "",
    phone: a.id ? nationalNumber(a.phone, dial) : ownNumber(me?.phone, dial),
    alt: nationalNumber(a.alt || "", dial),
    pin: a.pin || "",
    line: a.line || "",
    area: a.area || "",
    landmark: a.landmark || "",
    town: a.town || "",
    state_id: a.state_id ? String(a.state_id) : "",
  };
}

/* The shop names a field in its error; a few of its names differ from ours. */
const FIELD = { city: "town", state_id: "state", country_id: "country" };

export default function AddressForm({ initial, meta: startMeta, me, onSave, onCancel, saveLabel = "Save address" }) {
  /* The country being filled in, and the shop's rules for it. A saved address
     opens in its own country; a new one where the shop says to start. */
  const [code, setCode] = useState(initial?.country_code || startMeta?.country?.code || "");
  const [meta, setMeta] = useState(startMeta);
  useEffect(() => { if (!code && startMeta?.country?.code) setCode(startMeta.country.code); }, [startMeta, code]);
  useEffect(() => {
    if (!code) return;
    if (startMeta?.country?.code === code) { setMeta(startMeta); return; }
    let live = true;
    api(`/addresses/form?country=${encodeURIComponent(code)}`).then((m) => { if (live && m?.ok) setMeta(m); }).catch(() => {});
    return () => { live = false; };
  }, [code, startMeta]);
  const countries = meta?.countries || startMeta?.countries || [];
  const dial = meta?.phone?.dial || "";
  const phoneLen = meta?.phone?.length || 0;
  const pinLen = meta?.pin_length || 0;
  const states = meta?.states || [];
  const [d, setD] = useState(() => draftFrom(initial, me, dial));
  const [err, setErr] = useState({});
  const [saving, setSaving] = useState(false);
  const [look, setLook] = useState(null); /* {busy} | {ok, town, state, areas} | {ok:false} */
  /* Which of town/state the lookup filled, so a later pincode may refill them
     but never overwrite what the shopper typed. */
  const auto = useRef({ town: false, state: false, phone: false });
  const lastPin = useRef(initial?.pin || "");

  /* The form meta can arrive after the form opens: the prefix is only known
     then, so a number prefilled from the account is re-read against it. */
  useEffect(() => {
    if (dial) setD((x) => ({ ...x, phone: nationalNumber(x.phone, dial), alt: nationalNumber(x.alt, dial) }));
  }, [dial]);
  /* So can the signed-in account: a new address is for them unless they say
     otherwise, so their name and number fill any box still empty. */
  useEffect(() => {
    if (initial?.id || !me) return;
    setD((x) => {
      const next = { ...x, name: x.name || me.name || "", phone: x.phone || ownNumber(me.phone, dial) };
      if (!x.phone && next.phone) auto.current.phone = true;
      setErr((e) => ({ ...e, name: next.name ? undefined : e.name, phone: next.phone ? undefined : e.phone }));
      return next;
    });
  }, [me?.name, me?.phone, dial]); // eslint-disable-line

  useEffect(() => {
    const pin = d.pin;
    if (!meta?.pin_lookup || meta.country?.code !== code || pin.length !== pinLen || pin === lastPin.current) return;
    lastPin.current = pin;
    let live = true;
    setLook({ busy: true });
    api(`/pincode/${pin}`, { raw: true }).then((r) => {
      if (!live) return;
      setLook(r?.ok ? r : { ok: false });
      if (!r?.ok) return;
      setD((x) => {
        const next = { ...x };
        if (r.town && (!x.town || auto.current.town)) { next.town = r.town; auto.current.town = true; }
        if (r.state_id && (!x.state_id || auto.current.state)) { next.state_id = String(r.state_id); auto.current.state = true; }
        return next;
      });
      setErr((e) => ({ ...e, town: undefined, state: undefined }));
    });
    return () => { live = false; };
  }, [d.pin, pinLen, meta, code]);

  const pickCountry = (c) => {
    /* A new country has its own states and pincodes. The lines the shopper
       typed stay; the pincode, and whatever the old pincode filled in, go. */
    setCode(c);
    /* The account's own number was filled in for the old country; it comes
       back by itself if it belongs to the new one. */
    const filledTown = auto.current.town;
    const filledPhone = auto.current.phone;
    auto.current = { town: false, state: false, phone: false };
    lastPin.current = "";
    setLook(null);
    setD((x) => ({ ...x, pin: "", state_id: "", town: filledTown ? "" : x.town, phone: filledPhone ? "" : x.phone }));
    setErr((e) => ({ ...e, state: undefined, pin: undefined, phone: undefined, alt: undefined, country: undefined }));
  };

  const set = (k, v) => {
    if (k === "town") auto.current.town = false;
    if (k === "phone") auto.current.phone = false;
    if (k === "state_id") auto.current.state = false;
    setD((x) => ({ ...x, [k]: v }));
    setErr((e) => ({ ...e, [k === "state_id" ? "state" : k]: undefined, form: undefined }));
  };

  const check = () => {
    const x = {};
    const phoneOk = (v) => (phoneLen ? v.length === phoneLen : /^\d{6,15}$/.test(v));
    if (!d.name.trim()) x.name = "Enter the receiver's name";
    if (!phoneOk(d.phone)) x.phone = phoneLen ? `Enter a ${phoneLen}-digit mobile number` : "Enter a valid mobile number";
    if (d.alt && !phoneOk(d.alt)) x.alt = phoneLen ? `Enter a ${phoneLen}-digit number, or leave it empty` : "Enter a valid number";
    if (d.alt && d.alt === d.phone) x.alt = "Use a different number, or leave it empty";
    if (pinLen ? d.pin.length !== pinLen : !/^\d{3,10}$/.test(d.pin)) x.pin = pinLen ? `Enter a ${pinLen}-digit pincode` : "Enter a valid pincode";
    if (!d.line.trim()) x.line = "Enter the house no., building or apartment";
    if (!d.area.trim()) x.area = "Enter the road name, area or colony";
    if (!d.town.trim()) x.town = "Enter the city, district or town";
    if (states.length && !d.state_id) x.state = "Pick a state";
    return x;
  };

  const save = async (e) => {
    e.preventDefault();
    const x = check();
    setErr(x);
    if (Object.keys(x).length) return;
    setSaving(true);
    const body = {
      label: d.label, name: d.name.trim(), phone: d.phone, alt: d.alt,
      pin: d.pin, line: d.line.trim(), area: d.area.trim(), landmark: d.landmark.trim(),
      town: d.town.trim(), state_id: d.state_id ? Number(d.state_id) : false,
      country_id: code,
    };
    if (initial?.lat || initial?.lng) Object.assign(body, { lat: initial.lat, lng: initial.lng });
    const r = await onSave(body);
    setSaving(false);
    if (r?.error) {
      const f = FIELD[r.error.field] || r.error.field;
      setErr(f && f in { ...d, state: 1, country: 1 } ? { [f]: r.error.message } : { form: r.error.message || "Could not save that address. Try again." });
    }
  };

  const field = (k, label, { digits, ac, prefix } = {}) => (
    <label className={"co-field" + (prefix !== undefined ? " af-pre-field" : "") + (err[k] ? " co-err" : "")}
      style={prefix !== undefined ? { "--af-pre": Math.max(prefix.length, 3) } : undefined}>
      {prefix !== undefined && <b className="af-pre" aria-hidden="true">{prefix || "+"}</b>}
      <input value={d[k]} placeholder=" "
        onChange={(e) => set(k, digits ? e.target.value.replace(/\D/g, "").slice(0, digits) : e.target.value)}
        inputMode={digits ? "numeric" : undefined} autoComplete={ac} aria-invalid={!!err[k]} />
      <span>{label}</span>
      {err[k] && <em key={err[k]}>{err[k]}</em>}
    </label>
  );

  const place = look?.ok ? [look.town, look.state].filter(Boolean).join(", ") : "";
  /* The pickers' options: typing matches a name, a code ("IN", "TN") or a dial
     code ("+91", "91"). */
  const countryOpts = useMemo(() => countries.map((c) => ({
    value: c.code, label: c.name, hint: c.dial,
    search: `${c.name} ${c.code} ${c.dial.replace("+", "")}`.toLowerCase(),
  })), [countries]);
  const top = (meta?.suggested || []).map((c) => countryOpts.find((o) => o.value === c)).filter(Boolean);
  const stateOpts = useMemo(() => states.map((st) => ({
    value: String(st.id), label: st.name, hint: st.code, search: `${st.name} ${st.code}`.toLowerCase(),
  })), [states]);
  return (
    <form className="co-addr-form af-form" onSubmit={save} noValidate>
      <div className="af-top">
        <div className="co-chips" role="radiogroup" aria-label="Address type">
          {LABELS.map((l) => (
            <button type="button" key={l} role="radio" aria-checked={d.label === l} className={d.label === l ? "co-on" : ""} onClick={() => set("label", l)}>{l}</button>
          ))}
        </div>
      </div>
      <div className="co-form-grid">
        <Pick className="co-span2" label="Country" value={code} options={countryOpts}
          groups={[{ label: "Suggested", items: top }, { label: "All countries", items: countryOpts }]}
          onChange={(c) => c !== code && pickCountry(c)} disabled={!countryOpts.length}
          placeholder="Loading countries…" searchLabel="Search country or code, e.g. +91" error={err.country} />
        {field("name", "Full name", { ac: "name" })}
        {field("phone", "Mobile number", { digits: phoneLen || 15, ac: "tel-national", prefix: dial })}
        {field("alt", "Alternate mobile (optional)", { digits: phoneLen || 15, ac: "off", prefix: dial })}
        <div className="af-pin">
          {field("pin", "Pincode", { digits: pinLen || 10, ac: "postal-code" })}
          {look?.busy && <span className="af-hint"><i className="af-spin" />Finding your area…</span>}
          {!err.pin && place && <span className="af-hint af-good">{place}</span>}
        </div>
        <div className="co-span2">{field("line", "House no., building, apartment", { ac: "address-line1" })}</div>
        <div className="co-span2">
          {field("area", "Road name, area, colony", { ac: "address-line2" })}
          {look?.areas?.length > 0 && !look.areas.includes(d.area) && (
            <div className="af-areas" role="group" aria-label="Areas for this pincode">
              <small>Areas in {d.pin}</small>
              {look.areas.map((a) => <button type="button" key={a} onClick={() => set("area", a)}>{a}</button>)}
            </div>
          )}
        </div>
        {field("town", "City / District / Town", { ac: "address-level2" })}
        {!meta || states.length > 0 ? (
          <Pick label="State" value={d.state_id} options={stateOpts} onChange={(v) => set("state_id", v)}
            disabled={!meta} placeholder={meta ? "Select state" : "Loading…"} searchLabel="Search state"
            error={err.state} />
        ) : <span />}
        <div className="co-span2">{field("landmark", "Landmark (optional)", { ac: "off" })}</div>
      </div>
      {err.form && <p className="co-error" key={err.form}>{err.form}</p>}
      <div className="co-row-end">
        {onCancel && <button type="button" className="co-ghost" onClick={onCancel}>Cancel</button>}
        <button className="co-primary" type="submit" disabled={saving || !meta}>{saving ? "Saving…" : saveLabel}</button>
      </div>
    </form>
  );
}
