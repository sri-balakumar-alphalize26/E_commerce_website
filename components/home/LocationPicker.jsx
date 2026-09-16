"use client";
/* ==========================================================================
   369 Mart — Delivery location picker
   Tap the location in the header → popover springs open from the button
   (bottom sheet on phones). Map strip with a dropping pin + radar rings,
   "Use current location" (locating animation), pincode check, saved
   addresses with animated selection. Header text rolls to the new address.
   ========================================================================== */
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { Icon } from "./shared";

export const SAMPLE_ADDRESSES = [
  { id: "home", label: "Home", line: "Flat 4B, Palm Grove Apartments, MG Road", city: "Kochi 682016", icon: "home" },
  { id: "work", label: "Work", line: "3rd Floor, Tech Park Tower, Kazhakkoottam", city: "Thiruvananthapuram 695582", icon: "brief" },
  { id: "other", label: "Parents", line: "Near Clock Tower, Chinnakada", city: "Kollam 691001", icon: "pin" },
];

/* sample serviceability: Kerala pincodes start 67–69 */
const demoCheck = async (pin) => {
  await new Promise((r) => setTimeout(r, 900));
  if (!/^6[789]\d{4}$/.test(pin)) return { ok: false, error: "We don't deliver to this pincode yet." };
  return { ok: true, quick: pin.startsWith("68") || pin.startsWith("69"), eta: "13 mins" };
};

export default function LocationPicker({ open, onClose, anchorSelector = ".hm-loc", addresses = SAMPLE_ADDRESSES, selected, onSelect, onCheckPincode = demoCheck, onLocate }) {
  const [phase, setPhase] = useState("closed");
  const [pos, setPos] = useState(null);
  const [pin, setPin] = useState("");
  const [check, setCheck] = useState(null); // {busy} | {ok, …} | {ok:false, error}
  const [locating, setLocating] = useState("");
  const [shake, setShake] = useState(0);
  const card = useRef(null);

  useEffect(() => {
    if (open && phase === "closed") {
      const r = document.querySelector(anchorSelector)?.getBoundingClientRect();
      const vw = document.documentElement.clientWidth;
      setPos(!r || vw < 600 ? { sheet: true } : { sheet: false, x: Math.min(Math.max(16, r.left), vw - 16 - 400), y: r.bottom + 10, ox: Math.max(20, r.left + 24 - Math.min(Math.max(16, r.left), vw - 416)) });
      setPin(""); setCheck(null); setLocating("");
      setPhase("open");
    }
    if (!open && phase === "open") setPhase("closing");
  }, [open]); // eslint-disable-line

  useLayoutEffect(() => {
    if (phase === "open") document.documentElement.classList.add("lp-lock");
    if (phase === "closing") {
      const t = setTimeout(() => { setPhase("closed"); document.documentElement.classList.remove("lp-lock"); document.querySelector(anchorSelector)?.focus({ preventScroll: true }); }, 260);
      return () => clearTimeout(t);
    }
  }, [phase]); // eslint-disable-line

  useEffect(() => {
    if (phase !== "open") return;
    const k = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", k);
    card.current?.querySelector("button, input")?.focus({ preventScroll: true });
    return () => window.removeEventListener("keydown", k);
  }, [phase, onClose]);

  if (phase === "closed") return null;

  const locate = () => {
    setLocating("busy");
    const finish = (addr) => { setLocating("done"); setTimeout(() => { onSelect(addr); onClose(); }, 650); };
    const fallback = (msg) => { setLocating(msg); };
    if (!navigator.geolocation) return fallback("Location isn't available in this browser.");
    navigator.geolocation.getCurrentPosition(
      async ({ coords }) => {
        const found = onLocate ? await onLocate(coords) : null; /* reverse-geocode on your server */
        finish(found || { id: "current", label: "Current location", line: `${coords.latitude.toFixed(4)}, ${coords.longitude.toFixed(4)}`, city: "", icon: "gps" });
      },
      () => fallback("Allow location access, or enter a pincode below."),
      { enableHighAccuracy: true, timeout: 8000 }
    );
  };

  const submitPin = async (e) => {
    e.preventDefault();
    if (!/^\d{6}$/.test(pin)) { setCheck({ ok: false, error: "Enter a 6-digit pincode." }); setShake((s) => s + 1); return; }
    setCheck({ busy: true });
    const r = await onCheckPincode(pin);
    setCheck(r);
    if (!r.ok) setShake((s) => s + 1);
  };

  return (
    <div className={"lp-root lp-" + phase}>
      <div className="lp-back" onClick={onClose} />
      <div ref={card} className={"lp-card" + (pos?.sheet ? " lp-sheet" : "")} role="dialog" aria-modal="true" aria-label="Choose delivery location"
        style={pos && !pos.sheet ? { left: pos.x, top: pos.y, "--ox": pos.ox + "px" } : undefined}>
        <div className="lp-map" aria-hidden="true">
          <svg className="lp-roads" viewBox="0 0 400 110" preserveAspectRatio="none">
            <path d="M-10 78 C 80 60, 140 96, 230 70 S 360 40, 420 58" />
            <path d="M120 -10 C 130 40, 110 80, 150 130" />
            <path d="M300 -10 C 280 30, 320 70, 290 130" />
            <path className="lp-route" d="M40 96 C 110 90, 150 60, 200 56" />
          </svg>
          <span className="lp-ring" /><span className="lp-ring lp-r2" /><span className="lp-ring lp-r3" />
          <span className={"lp-pin" + (locating === "busy" ? " lp-hop" : "")} key={selected?.id}>
            <svg viewBox="0 0 24 24"><path d="M12 22s-7-6.2-7-12a7 7 0 0 1 14 0c0 5.8-7 12-7 12z" /><circle cx="12" cy="10" r="2.6" /></svg>
          </span>
          <span className="lp-shadow" />
          <div className="lp-map-txt">
            <small>Delivering to</small>
            <b key={selected?.id}>{selected?.label || "Choose a location"}</b>
          </div>
          <button className="lp-x" onClick={onClose} aria-label="Close"><Icon n="x" size={16} /></button>
        </div>

        <div className="lp-body">
          <button className={"lp-gps lp-in" + (locating === "busy" ? " lp-busy" : "") + (locating === "done" ? " lp-ok" : "")} style={{ "--i": 0 }} onClick={locate} disabled={locating === "busy"}>
            <span className="lp-gps-ic"><Icon n={locating === "done" ? "check" : "gps"} size={18} /></span>
            <span className="lp-gps-txt">
              <b>{locating === "busy" ? "Finding your location…" : locating === "done" ? "Location found" : "Use my current location"}</b>
              <small>{locating && locating !== "busy" && locating !== "done" ? locating : "Faster delivery with precise location"}</small>
            </span>
            <Icon n="right" size={16} />
          </button>

          <form className="lp-pin-form lp-in" style={{ "--i": 1 }} onSubmit={submitPin} noValidate>
            <label htmlFor="lp-pin">Check delivery by pincode</label>
            <div key={shake} className={"lp-pin-row" + (check && check.ok === false ? " lp-shake" : "")}>
              <input id="lp-pin" inputMode="numeric" maxLength={6} placeholder="e.g. 682016" value={pin}
                onChange={(e) => { setPin(e.target.value.replace(/\D/g, "").slice(0, 6)); setCheck(null); }} />
              <button type="submit" disabled={check?.busy}>{check?.busy ? <span className="lp-spin" /> : "Check"}</button>
            </div>
            {check && !check.busy && (
              <p className={"lp-result " + (check.ok ? "lp-good" : "lp-bad")} role="status">
                <Icon n={check.ok ? (check.quick ? "bolt" : "truck") : "info"} size={14} className={check.ok && check.quick ? "hm-fill" : ""} />
                {check.ok ? (check.quick ? `Quick delivery available · in ${check.eta}` : "Express delivery available · 2–5 days") : check.error}
              </p>
            )}
          </form>

          <div className="lp-saved">
            <h4 className="lp-in" style={{ "--i": 2 }}>Saved addresses</h4>
            <ul>
              {addresses.map((a, i) => {
                const on = selected?.id === a.id;
                return (
                  <li key={a.id} className="lp-in" style={{ "--i": 3 + i }}>
                    <button className={"lp-addr" + (on ? " lp-on" : "")} aria-pressed={on} onClick={() => { onSelect(a); setTimeout(onClose, 380); }}>
                      <span className="lp-addr-ic"><Icon n={a.icon || "pin"} size={17} /></span>
                      <span className="lp-addr-txt"><b>{a.label}</b><small>{a.line}{a.city ? `, ${a.city}` : ""}</small></span>
                      <span className="lp-radio" aria-hidden="true"><i /></span>
                    </button>
                  </li>
                );
              })}
            </ul>
            <button className="lp-add lp-in" style={{ "--i": 3 + addresses.length }}><Icon n="plus" size={16} />Add a new address</button>
          </div>
        </div>
      </div>
    </div>
  );
}
