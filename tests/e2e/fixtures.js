/* Shared setup for the admin end-to-end tests.
 *
 * The important rule here is that **no test ever touches the live home page.**
 * Each run duplicates it, works entirely on the copy, and deletes the copy
 * afterwards. Before this existed, every check was a scratchpad script editing
 * the real page and hand-restoring the banner text and row order at the end;
 * one missed restore silently changed what shoppers see.
 */
import { test as base, expect } from "@playwright/test";

export const ODOO = process.env.MART_ODOO_URL || "http://localhost:8097";
const LOGIN = process.env.MART_LOGIN || "admin";
const PASSWORD = process.env.MART_PASSWORD || "admin";

export const test = base.extend({
  /* Signed in, with helpers that speak to the admin API.
   *
   * Deliberately `context.request` and not the top-level `request` fixture:
   * that one has its own cookie jar, so signing in there would leave the
   * browser signed out and every test would redirect to /login. */
  api: async ({ context }, use) => {
    const req = context.request;
    const signIn = await req.post("/api/auth/login", {
      data: { login: LOGIN, password: PASSWORD },
    });
    expect(signIn.ok(), "sign-in failed — is the dev server up?").toBeTruthy();

    const call = async (path, init = {}) => {
      const r = await req.fetch("/api/mart" + path, init);
      const body = await r.json().catch(() => null);
      expect(r.status(), `${init.method || "GET"} ${path} -> ${JSON.stringify(body)}`)
        .toBeLessThan(400);
      return body;
    };

    await use({
      get: (p) => call(p),
      post: (p, data) => call(p, { method: "POST", data }),
      patch: (p, data) => call(p, { method: "PATCH", data }),
      del: (p) => call(p, { method: "DELETE" }),
      /* The shop's own feed — the only honest answer to "what do shoppers
         actually get?". Read straight from Odoo rather than through the
         proxy, so a cached copy can never make a failing test look green. */
      feed: async (mode = "quick") => {
        const r = await req.get(`${ODOO}/369mart/home/${mode}`);
        expect(r.ok()).toBeTruthy();
        return r.json();
      },
    });
  },

  /* A throwaway copy of the live page, deleted however the test ends. */
  pageId: async ({ api }, use) => {
    const made = await api.post("/admin/home/pages", { name: `E2E ${Date.now()}` });
    const id = made.page.id;
    try {
      await use(id);
    } finally {
      await api.del(`/admin/home/pages/${id}`).catch(() => {});
    }
  },

  /* Anything the screen logged. A test that passes while the console is full
     of errors is not telling the truth. */
  problems: async ({ page }, use) => {
    const found = [];
    page.on("pageerror", (e) => found.push(`pageerror: ${e.message}`));
    page.on("console", (m) => m.type() === "error" && found.push(`console: ${m.text()}`));
    page.on("response", (r) => r.status() >= 400 && found.push(`${r.status()} ${r.url()}`));
    await use(found);
  },
});

/* Open the editor on a page and wait until it has actually drawn. */
export async function openEditor(page, id) {
  await page.goto(`/admin/home/${id}`, { waitUntil: "domcontentloaded" });
  await page.waitForSelector(".pe-band", { state: "attached" });
  await page.waitForFunction(() => !document.querySelector(".pe-loading"));
}

/* What the canvas is showing, group by group. */
export const GROUPS = {
  tab: ".pe-tabs",
  banner: ".pe-banners",
  tile: ".pe-tiles",
  section: ".pe-sections",
};

export function bands(page, kind) {
  return page.locator(`${GROUPS[kind]} .pe-band`);
}

export { expect };
