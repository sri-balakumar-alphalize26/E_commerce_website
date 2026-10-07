/* Live tracking on the order page - screenshots and a smoke check.
 *
 * Needs an order that is out for delivery, owned by whoever is signed in:
 *
 *   MART_TRACK_ORDER=369M-2609302111   the order to open
 *   MART_SESSION=<odoo session id>      that customer's session (optional -
 *                                       otherwise MART_LOGIN/MART_PASSWORD
 *                                       sign in through /api/auth/login)
 *   MART_BASE_URL=http://localhost:3000 the running site
 *
 * Saves docs/screenshots/live-tracking-{desktop,phone}.png. It reads only:
 * nothing on the order is changed.
 */
import { test, expect } from "@playwright/test";

const ORDER = process.env.MART_TRACK_ORDER;
const SESSION = process.env.MART_SESSION;

test.skip(!ORDER, "Set MART_TRACK_ORDER to an out-for-delivery order to run this.");

async function signIn(context, baseURL) {
  /* MART_SKIP_PHONE_GATE=1: a test account with no proven mobile number is
     sent to "Add your mobile number" first (mart369_auth's needPhone). For
     screenshots of somebody else's flow-test order that gate is in the way;
     this tells only this browser it is passed. Nothing is written anywhere. */
  if (process.env.MART_SKIP_PHONE_GATE) {
    await context.route("**/api/auth/me", async (route) => {
      const response = await route.fetch();
      const body = await response.json().catch(() => null);
      await route.fulfill({ response, json: body && { ...body, needPhone: false } });
    });
  }
  if (SESSION) {
    await context.addCookies([{ name: "mart_session", value: SESSION, url: baseURL, httpOnly: true, sameSite: "Lax" }]);
    return;
  }
  const r = await context.request.post("/api/auth/login", {
    data: { login: process.env.MART_LOGIN || "admin", password: process.env.MART_PASSWORD || "admin" },
  });
  expect(r.ok(), "sign-in failed — is the dev server up?").toBeTruthy();
}

for (const [label, size] of [["desktop", { width: 1400, height: 1000 }], ["phone", { width: 390, height: 844 }]]) {
  test(`live tracking card — ${label}`, async ({ browser, baseURL }) => {
    const context = await browser.newContext({ viewport: size });
    await signIn(context, baseURL);
    const page = await context.newPage();

    const polled = page.waitForResponse((r) => r.url().includes(`/api/mart/orders/${ORDER}/track`) && r.ok(), { timeout: 60000 });
    await page.goto(`/track/${ORDER}`);
    const track = (await (await polled).json()).track;
    expect(track, "the order has a delivery job").toBeTruthy();
    expect(JSON.stringify(track)).not.toMatch(/token|\/wa\/track/);

    const card = page.locator(".ot-live");
    await expect(card).toBeVisible({ timeout: 30000 });
    await expect(page.locator(".ot-lm-home")).toBeVisible();
    await expect(page.locator(".ot-live-bar b")).toHaveText(track.label);
    // The rider card: the job's real name, or "Your rider" - never invented.
    await expect(page.locator(".ot-rider-card b")).toHaveText(track.rider.name || "Your rider");
    if (track.rider.phone) await expect(page.locator(`.ot-rider-card a[href="tel:${track.rider.phone}"]`)).toBeVisible();

    // Let the tiles land before the picture is taken.
    await page.waitForLoadState("networkidle").catch(() => {});
    await page.waitForTimeout(1500);
    await page.locator(".ot-tracker").scrollIntoViewIfNeeded();
    await page.screenshot({ path: `docs/screenshots/live-tracking-${label}.png`, fullPage: label === "phone" ? false : true });

    // It keeps polling while live.
    await page.waitForResponse((r) => r.url().includes(`/orders/${ORDER}/track`), { timeout: 15000 });
    await context.close();
  });
}
