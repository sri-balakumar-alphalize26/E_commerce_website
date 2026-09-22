"use client";

/* Where an invite code waits between the link and the sign-up form.
 *
 * A shopper who opens `/r/ABC369` usually looks around before making an
 * account, so the code cannot live in the URL - it would be gone by the time
 * they signed up. It goes in localStorage, and is cleared the moment it has
 * been used so a second account on the same browser is not credited to the
 * same inviter.
 *
 * Every read and write is wrapped: storage throws in a private window and in
 * some embedded browsers, and a referral is never worth failing a sign-up
 * over. */

const KEY = "369mart.referral";

export function rememberReferral(code) {
  const clean = String(code || "").trim().toUpperCase();
  if (!clean) return;
  try {
    localStorage.setItem(KEY, clean);
  } catch {
    /* No storage: the code is simply lost, and sign-up carries on. */
  }
}

export function takeReferral() {
  try {
    const code = localStorage.getItem(KEY) || "";
    return code.trim().toUpperCase();
  } catch {
    return "";
  }
}

/* Called once the code has actually been sent, so it is not spent twice. */
export function clearReferral() {
  try {
    localStorage.removeItem(KEY);
  } catch {
    /* Nothing to clear. */
  }
}
