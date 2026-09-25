/* How a saved address reads on screen. The shop sends every line apart
   (line, area, landmark, town, state, pin) and, for older records, only the
   joined `city` ("Dindigul 624003") - these helpers cope with both, so every
   card, header and receipt shows an address the same way. */

/* "Dindigul, Tamil Nadu 624003" - or the old joined city when that is all
   there is. */
export function placeLine(a) {
  if (!a) return "";
  if (a.town) return `${a.town}${a.state ? ", " + a.state : ""}${a.pin ? " " + a.pin : ""}`;
  return [a.city, a.state].filter(Boolean).join(", ");
}

/* The address as separate lines, top to bottom as a parcel label reads. */
export function addressLines(a) {
  if (!a) return [];
  /* "near the bus stand" - unless the shopper already wrote "Near …" or
     "Opposite …" themselves. */
  const mark = a.landmark && !/^(near|opp|opposite|behind|beside|next to)\b/i.test(a.landmark) ? "near " + a.landmark : a.landmark;
  const street = [a.area, mark].filter(Boolean).join(", ");
  return [a.line, street, placeLine(a)].filter(Boolean);
}

/* The same, on one line - headers and pickers. */
export function addressText(a) {
  return addressLines(a).join(", ");
}

/* The digits a shopper types, from the stored E.164 number: "+919486020356"
   with dial "+91" -> "9486020356". */
export function nationalNumber(phone, dial) {
  const p = String(phone || "").replace(/[^\d+]/g, "");
  const d = String(dial || "").replace(/\D/g, "");
  if (p.startsWith("+") && d && p.slice(1).startsWith(d)) return p.slice(1 + d.length);
  return p.replace(/^\+/, "");
}

/* "+91 9486020356" - the stored number is already international, so the
   prefix is never added twice. */
export function phoneText(phone, dial) {
  if (!phone) return "";
  if (!dial) return phone;
  return `${dial} ${nationalNumber(phone, dial)}`;
}
