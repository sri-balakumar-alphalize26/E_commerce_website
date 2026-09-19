/* ==========================================================================
   369 Mart — the account's own things: the wallet, saved payments, reviews,
   notifications, invites and scratch cards.

   Each of these was a `369mart.*` key in this browser, seeded with a handful
   of invented rows that every visitor was shown as their own history: a ₹100
   welcome bonus nobody was given, a Visa ending 4821 nobody owns, a referral
   from an Anu R. who does not exist. They are one customer's records, so they
   belong to the shop. This file is the single seam they come through.
   ========================================================================== */
import { useCallback } from "react";
import { api } from "@/lib/api";
import { useAction, useResource } from "@/lib/useFetch";

/* One of the account's things: what the shop says, and a way to ask it to
   change. `data` is null until the first answer arrives - a screen shows its
   own skeleton rather than a shape invented here, because "nothing saved" and
   "not here yet" are different sentences and only one of them is true.

   `send` posts to whichever route does the writing, then re-reads this one:
   the reply is the record, and nothing is patched locally to look like it. */
export function useRemote(path, { enabled = true } = {}) {
  const { data, loading, error, reload } = useResource(path, { enabled });
  const act = useAction();
  const send = useCallback(
    (to, options) =>
      act.run(async () => {
        const answer = await api(to, options);
        api.invalidate(path);
        await reload();
        return answer ?? true;
      }),
    [act, path, reload],
  );
  return { data, loading, error, reload, send, busy: act.busy, sendError: act.error };
}

export const STAR_WORDS = ["", "Terrible", "Bad", "Okay", "Good", "Excellent"];

/* How many friends the progress bar draws. Not money and not a promise: what
   a referral pays is the shop's setting and arrives with the invite list.
   There was a REFER_BONUS = 500 here for a milestone nothing pays. */
export const REFER_GOAL = 5;

/* ---------- time labels ---------- */
export function ago(t, now = Date.now()) {
  const s = Math.max(0, Math.round((now - t) / 1000));
  if (s < 60) return "Just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  if (s < 86400 * 7) return `${Math.floor(s / 86400)} d ago`;
  return new Date(t).toLocaleDateString("en-IN", { day: "numeric", month: "short" });
}
export const fmtDate = (t) => new Date(t).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
export const fmtDateTime = (t) => new Date(t).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });
