"use client";

/* Times, for the console.

   Lifted out of adminData.js, which is the sample-data file and is going away.
   Everything here was pinned to that file's frozen clock: `since()` defaulted
   to a `TODAY` in September 2026, so a screen reading it told an operator that
   an order placed a minute ago was eleven months old. Here "now" is now.

   Still hand-rolled rather than `toLocaleString`, and that is deliberate -
   adminData.js's own comment records why. Node and the browser disagree about
   some en-IN output ("Sept" vs "Sep"), and React reports the difference as a
   hydration mismatch (error #418).

   Money is not here. The console used to glue a rupee sign to a number; the
   shop says what its money looks like and lib/money.js prints what it is told. */

const HOUR = 3600000;
const IST = 5.5 * HOUR;
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const WEEKDAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];

export const clock = (t) => {
  const d = new Date(t + IST), h = d.getUTCHours(), m = d.getUTCMinutes();
  return `${h % 12 || 12}:${String(m).padStart(2, "0")} ${h < 12 ? "am" : "pm"}`;
};
export const dateShort = (t) => { const d = new Date(t + IST); return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]}`; };
export const dateLong = (t) => { const d = new Date(t + IST); return `${WEEKDAYS[d.getUTCDay()]}, ${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`; };
/* "17 Sep 2026" - a date that may be from another year, like when somebody joined. */
export const dateYear = (t) => { const d = new Date(t + IST); return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`; };
export const dateTime = (t) => `${dateShort(t)}, ${clock(t)}`;

/* How long ago, and - for a promise that has already passed - how overdue.
   `now` is a real clock by default, and is only passed in by tests. */
export const since = (t, now = Date.now()) => {
  const m = Math.max(0, Math.round((now - t) / 60000));
  return m < 1 ? "just now" : m < 60 ? `${m} min ago` : m < 1440 ? `${Math.floor(m / 60)} h ago` : `${Math.floor(m / 1440)} d ago`;
};

/* "due in 14 min": the countdown to a promise that can still be kept. */
export const dueIn = (due, now = Date.now()) => {
  const m = Math.max(0, Math.round((due - now) / 60000));
  if (m < 1) return "due now";
  if (m < 60) return `due in ${m} min`;
  if (m < 1440) return `due in ${Math.floor(m / 60)} h${m % 60 ? ` ${m % 60} min` : ""}`;
  return `due in ${Math.floor(m / 1440)} d`;
};

/* "6 min late". Reads the other way round from `since`, because an operator
   looking at an overdue order is counting up, not back. */
export const overdueBy = (due, now = Date.now()) => {
  const m = Math.max(0, Math.round((now - due) / 60000));
  return m < 60 ? `${m} min late` : m < 1440 ? `${Math.floor(m / 60)} h late` : `${Math.floor(m / 1440)} d late`;
};
