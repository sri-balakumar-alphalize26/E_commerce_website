/* A mobile number, by the rule of the country it is for.

   The rule comes from the shop (mart369_auth `_mart369_phone_hint`, read off
   Google's libphonenumber): { dial: "+91", length: 10, starts: "6789",
   example, country }. Nothing here knows any country - India's "ten digits,
   starting 6, 7, 8 or 9" is just what the shop sends for IN. */

/* What may stay in the box as it is typed: digits only, a pasted +country
   code or leading 0 taken off, a first digit no mobile there starts with
   refused, and never longer than the country's number. */
export function cleanMobile(value, rule) {
  let v = String(value ?? "").replace(/\D/g, "");
  const len = rule?.length || 0;
  const cc = String(rule?.dial || "").replace(/\D/g, "");
  if (len && cc && v.length > len && v.startsWith(cc)) v = v.slice(cc.length);
  if (len && v.length > len && v.startsWith("0")) v = v.replace(/^0+/, "");
  const starts = rule?.starts || "";
  if (starts) while (v && !starts.includes(v[0])) v = v.slice(1);
  return len ? v.slice(0, len) : v.slice(0, 15);
}

/* "6, 7, 8 or 9" */
export function startsText(starts) {
  const d = String(starts || "").split("");
  if (d.length <= 1) return d.join("");
  return `${d.slice(0, -1).join(", ")} or ${d[d.length - 1]}`;
}

/* The message for a number that is not complete yet; "" when it is fine. */
export function mobileError(value, rule, { required = true } = {}) {
  const v = String(value || "");
  if (!v) return required ? "Enter the mobile number" : "";
  const len = rule?.length || 0;
  if (rule?.starts && !rule.starts.includes(v[0])) {
    return `${rule.country ? rule.country + " mobile" : "Mobile"} numbers start with ${startsText(rule.starts)}`;
  }
  if (len ? v.length !== len : !/^\d{6,15}$/.test(v)) {
    return len ? `Enter a ${len}-digit mobile number` : "Enter a valid mobile number";
  }
  return "";
}

/* The line under the box: "10 digits, starts with 6, 7, 8 or 9". */
export function mobileHint(rule) {
  if (!rule?.length) return "";
  return rule.starts ? `${rule.length} digits, starts with ${startsText(rule.starts)}` : `${rule.length} digits`;
}

/* The rule for a country, from the shop (cached: a country's rule does not
   change while the page is open). */
const cache = new Map();
export function fetchMobileRule(country) {
  const key = String(country || "").toUpperCase();
  if (!cache.has(key)) {
    const q = key ? `?country=${encodeURIComponent(key)}` : "";
    cache.set(key, fetch(`/api/auth/phone-form${q}`).then((r) => r.json()).then((r) => r?.phone || null)
      .catch(() => { cache.delete(key); return null; }));
  }
  return cache.get(key);
}
