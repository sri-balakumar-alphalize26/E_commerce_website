/* The admin home-page editor.
 *
 * These tests exist because of one bug, and the first of them is written to
 * catch that whole class rather than that one instance.
 *
 * The editor reuses the storefront's own `.hm-banner-track`, which is a
 * two-wide scrolling carousel that the shop drives with arrow buttons.
 * Rendering bare banners into it inherited the fixed width and the hidden
 * scrollbar but not the arrows — so banners three and four were live on the
 * shop and could not be seen, selected, edited or reordered from the screen
 * whose whole job is editing them. Nothing failed. Nothing was logged. The
 * page simply did not show two of the things it owned.
 *
 * "Can every band be reached?" is the question that catches that, and it will
 * catch the next one too, which will not be banners.
 */
import { test, expect, openEditor, bands, GROUPS } from "./fixtures.js";

const KINDS = ["tab", "banner", "tile", "section"];

/* No band may sit outside the box its group actually shows.
 *
 * Deliberately measured per band rather than as `scrollWidth > clientWidth` on
 * the group. The rails inside a Row are the shop's own horizontal scrollers and
 * their arrow buttons are positioned 14px outside their container on purpose,
 * so the whole-container form of this check fails on a page that is perfectly
 * fine. A product inside a rail is not something this screen edits; a band is.
 * What must never happen is a *band* being parked in an overflow nobody can
 * scroll to — which is exactly how two live banners went missing. */
async function assertEveryBandIsReachable(page) {
  /* Polled, not measured once. Toggling "Show hidden" re-flows the tab row and
     the banner grid, and a single measurement taken mid-reflow reports bands
     out of bounds that land back inside a frame later — a failure about the
     test's timing rather than about the page. */
  const measure = () => page.evaluate((groups) => {
    const bad = [];
    for (const [kind, sel] of Object.entries(groups)) {
      const group = document.querySelector(sel);
      if (!group) continue;
      const box = group.getBoundingClientRect();
      for (const [i, band] of [...group.querySelectorAll(".pe-band")].entries()) {
        const r = band.getBoundingClientRect();
        /* 1px absorbs sub-pixel rounding, which browsers do produce here. */
        if (r.width < 1 || r.height < 1) { bad.push(`${kind} #${i}: not rendered`); continue; }
        if (r.right > box.right + 1 || r.left < box.left - 1) {
          bad.push(`${kind} #${i}: ${Math.round(r.left)}..${Math.round(r.right)} `
            + `outside ${Math.round(box.left)}..${Math.round(box.right)}`);
        }
      }
    }
    return bad;
  }, GROUPS);

  await expect.poll(measure, {
    message: "a band is outside its group's visible box — it cannot be clicked, "
      + "edited or reordered, and nothing on screen says it is there",
    timeout: 15000,
  }).toEqual([]);
}

test.describe("the canvas shows everything it owns", () => {
  test("every band is inside its group's visible box", async ({ page, pageId }) => {
    await openEditor(page, pageId);
    await assertEveryBandIsReachable(page);

    /* And with the switched-off bands brought back, which is when the tab row
       goes from seven to fourteen. */
    const toggle = page.locator(".pe-showhidden input");
    if (await toggle.count()) {
      await toggle.check();
      await page.waitForTimeout(400);
      await assertEveryBandIsReachable(page);
    }
  });

  test("every band has a usable drag handle", async ({ page, pageId }) => {
    await openEditor(page, pageId);
    for (const kind of KINDS) {
      const all = bands(page, kind);
      const n = await all.count();
      for (let i = 0; i < n; i++) {
        const box = await all.nth(i).locator(".pe-grip").boundingBox();
        expect(box, `${kind} #${i} has no reachable drag handle`).not.toBeNull();
        expect(box.width, `${kind} #${i} handle is zero-width`).toBeGreaterThan(0);
      }
    }
  });
});

test.describe("the canvas is the shop", () => {
  test("same bands, same order, as the payload says", async ({ page, api, pageId }) => {
    /* The copy is not the live page, so compare it against its own builder
       payload — the live feed describes a different page. */
    await openEditor(page, pageId);
    const data = await api.get(`/admin/home/pages/${pageId}/builder?mode=quick`);
    const live = (rows) => (rows || []).filter((r) => r.active);

    expect(await bands(page, "tab").count()).toBe(live(data.preview.tabs).length);
    expect(await bands(page, "banner").count()).toBe(live(data.preview.banners).length);
    expect(await bands(page, "tile").count()).toBe(live(data.preview.categories).length);
    expect(await bands(page, "section").count()).toBe(live(data.preview.sections).length);

    /* Order, not just count: a page with the right bands in the wrong order is
       still the wrong page. */
    const shown = await page.locator(".pe-banners .pe-band strong").allTextContents();
    expect(shown.map((s) => s.trim()))
      .toEqual(live(data.preview.banners).map((b) => b.title));
  });

  test("show hidden adds exactly what it claims", async ({ page, pageId }) => {
    await openEditor(page, pageId);
    const label = page.locator(".pe-showhidden");
    test.skip(!(await label.count()), "this page has no hidden bands");

    const before = {};
    for (const k of KINDS) before[k] = await bands(page, k).count();
    const claimed = Number((await label.textContent()).match(/\((\d+)\)/)[1]);

    await label.locator("input").check();
    await page.waitForTimeout(400);
    let added = 0;
    for (const k of KINDS) added += (await bands(page, k).count()) - before[k];
    expect(added).toBe(claimed);
  });
});

test.describe("changes reach the shop", () => {
  test("an edit saves, and survives a reload", async ({ page, pageId }) => {
    await openEditor(page, pageId);
    await bands(page, "banner").first().click();

    /* By exact accessible name: the Kicker field's placeholder is "the small
       line above the headline", so a text match finds two inputs. */
    const headline = page.getByRole("textbox", { name: "Headline", exact: true });
    const text = `E2E headline ${Date.now()}`;
    await headline.fill(text);

    await expect(page.locator(".pe-chip")).toHaveText(/Saved/, { timeout: 60000 });
    /* The canvas is the storefront component, so the edit must show there too
       and not only in the field the operator typed into. */
    await expect(bands(page, "banner").first().locator("strong")).toHaveText(text);

    await page.reload({ waitUntil: "domcontentloaded" });
    await page.waitForSelector(".pe-band", { state: "attached" });
    await expect(bands(page, "banner").first().locator("strong")).toHaveText(text);
  });

  test("hiding a band takes it off the page, and the eye brings it back",
    async ({ page, pageId }) => {
      await openEditor(page, pageId);
      const before = await bands(page, "banner").count();
      const first = bands(page, "banner").first();
      const title = (await first.locator("strong").textContent()).trim();

      await first.locator(".pe-tool").nth(1).click();   /* the eye */
      await expect(page.locator(".pe-chip")).toHaveText(/Saved/, { timeout: 60000 });
      await expect(bands(page, "banner")).toHaveCount(before - 1);

      await page.locator(".pe-showhidden input").check();
      await page.waitForTimeout(400);
      const back = page.locator(".pe-banners .pe-band", { hasText: title }).first();
      await expect(back).toHaveClass(/pe-hidden/);
      await back.locator(".pe-tool").nth(1).click();
      await expect(page.locator(".pe-chip")).toHaveText(/Saved/, { timeout: 60000 });
      await expect(back).not.toHaveClass(/pe-hidden/);
    });
});

test.describe("reordering", () => {
  const titles = (page) => page.locator(".pe-sections .pe-band")
    .evaluateAll((els) => els.map((e) =>
      e.querySelector("h2, .pe-row-empty b")?.textContent?.trim() || "?"));

  test("with the keyboard, and it persists", async ({ page, pageId }) => {
    await openEditor(page, pageId);
    const before = await titles(page);
    test.skip(before.length < 2, "needs two rows to reorder");

    /* Space picks it up, arrow moves it, space drops it. This silently did
       nothing until the DndContext was scoped to each group: the arrow key
       resolved onto a band in a different group and the drop was discarded. */
    await page.locator(".pe-sections .pe-band .pe-grip").first().focus();
    /* A beat between each press. dnd-kit measures every droppable when the
       drag starts, and an arrow key that arrives in the same tick is resolved
       against measurements that do not exist yet. A person cannot type this
       fast; a test can, and then reports a bug that is not there. */
    await page.keyboard.press("Space");
    await page.waitForTimeout(400);
    await page.keyboard.press("ArrowDown");
    await page.waitForTimeout(400);
    await page.keyboard.press("Space");

    await expect.poll(() => titles(page)).not.toEqual(before);
    const after = await titles(page);
    expect(after[0]).toBe(before[1]);

    await page.reload({ waitUntil: "domcontentloaded" });
    await page.waitForSelector(".pe-band", { state: "attached" });
    await expect.poll(() => titles(page)).toEqual(after);
  });

  test("with the mouse, and it persists", async ({ page, pageId }) => {
    await openEditor(page, pageId);
    const before = await titles(page);
    test.skip(before.length < 2, "needs two rows to reorder");

    const from = page.locator(".pe-sections .pe-band .pe-grip").first();
    await from.scrollIntoViewIfNeeded();
    const a = await from.boundingBox();
    const target = await page.locator(".pe-sections .pe-band").nth(1).boundingBox();

    /* Travel in small steps with a beat between them, rather than one long
       jump to a coordinate measured before the drag began. dnd-kit shifts the
       other bands out of the way as you go, so that coordinate is stale by the
       time the pointer arrives and the drop lands nowhere. */
    await page.mouse.move(a.x + a.width / 2, a.y + a.height / 2);
    await page.mouse.down();
    for (let i = 1; i <= 10; i++) {
      await page.mouse.move(a.x + a.width / 2, a.y + a.height / 2 + (target.height * i) / 10,
        { steps: 3 });
      await page.waitForTimeout(120);
    }
    await expect(page.locator(".pe-dragging")).toHaveCount(1);
    await page.mouse.up();

    await expect.poll(() => titles(page)).not.toEqual(before);
    const after = await titles(page);
    await page.reload({ waitUntil: "domcontentloaded" });
    await page.waitForSelector(".pe-band", { state: "attached" });
    await expect.poll(() => titles(page)).toEqual(after);
  });
});

test.describe("the console stays quiet", () => {
  for (const [name, path] of [
    ["the dashboard", "/admin"],
    ["the home pages screen", "/admin/home"],
    ["a sample section", "/admin/orders"],
  ]) {
    test(`${name} loads with nothing logged`, async ({ page, api, problems }) => {
      await page.goto(path, { waitUntil: "domcontentloaded" });
      await page.waitForTimeout(4000);
      expect(problems).toEqual([]);
    });
  }

  test("the editor loads with nothing logged", async ({ page, pageId, problems }) => {
    await openEditor(page, pageId);
    await page.waitForTimeout(2000);
    expect(problems).toEqual([]);
  });
});

test.describe("adding and removing", () => {
  test("a new band lands on this page, and opens ready to name",
    async ({ page, api, pageId }) => {
      await openEditor(page, pageId);
      const before = await bands(page, "banner").count();

      await page.getByRole("button", { name: "Banner", exact: true }).click();
      await expect(bands(page, "banner")).toHaveCount(before + 1);

      /* It opens selected, because a new band is called "New banner" and sits
         at the bottom: leaving the operator to hunt for it is leaving them to
         wonder whether the button did anything. */
      await expect(page.locator(".pe-panel-head h2")).toHaveText("Banner");
      await expect(page.locator(".pe-panel-head p")).toHaveText("New banner");
      await expect(bands(page, "banner").last()).toHaveClass(/pe-on/);

      /* And on *this* page, not on whichever one happens to be live. */
      const data = await api.get(`/admin/home/pages/${pageId}/builder?mode=quick`);
      expect(data.preview.banners.some((b) => b.title === "New banner")).toBe(true);
    });

  test("removing takes it off the page and leaves it in the Trash",
    async ({ page, api, pageId }) => {
      await openEditor(page, pageId);
      await page.getByRole("button", { name: "Row", exact: true }).click();
      await expect(page.locator(".pe-panel-head p")).toHaveText("New row");

      const rows = await bands(page, "section").count();
      const trashBefore =
        (await api.get(`/admin/home/pages/${pageId}/builder?mode=quick`)).trash.length;

      await page.getByRole("button", { name: "Remove" }).click();
      /* The console's own dialog, not the browser's. */
      await page.getByRole("button", { name: /^Remove / }).click();
      await expect(bands(page, "section")).toHaveCount(rows - 1);

      const after = await api.get(`/admin/home/pages/${pageId}/builder?mode=quick`);
      expect(after.trash.length, "removing starts a clock, it does not delete")
        .toBe(trashBefore + 1);
    });
});

test.describe("the editor is styled", () => {
  /* The console's design tokens used to be declared on `.ad-app`, the shell.
     The editor is its own full-width route with no `.ad-app` ancestor, so
     every var() in it resolved to nothing — and an unresolved var is not an
     error. `background: var(--ad-green)` just goes transparent, so the panel's
     switch had no track at all and nothing anywhere said why. */
  test("every design token resolves on this route", async ({ page, pageId }) => {
    await openEditor(page, pageId);
    const unresolved = await page.evaluate(() => {
      const root = getComputedStyle(document.documentElement);
      const names = ["--ad-blue", "--ad-green", "--ad-red", "--ad-ink",
        "--ad-muted", "--ad-line", "--ad-ground", "--ad-card"];
      return names.filter((n) => !root.getPropertyValue(n).trim());
    });
    expect(unresolved, "these tokens are not defined on the editor route, so "
      + "every var() using them silently falls back to nothing").toEqual([]);
  });

  test("the panel's switch actually shows its state", async ({ page, pageId }) => {
    await openEditor(page, pageId);
    await bands(page, "section").first().click();
    const track = page.locator(".pe-panel .ad-switch i");
    const colour = await track.evaluate((el) => getComputedStyle(el).backgroundColor);
    expect(colour, "the switch track is transparent — on and off look the same")
      .not.toBe("rgba(0, 0, 0, 0)");
  });
});

test.describe("the controls behave", () => {
  test("the Remove button stays red under the pointer", async ({ page, pageId }) => {
    /* `.ad-btn:hover` is two classes and `.ad-danger` is one, so without a
       hover rule of its own the destructive button turns the same near-white
       as an ordinary one at exactly the moment the pointer is on it. */
    await openEditor(page, pageId);
    await bands(page, "section").first().click();
    const remove = page.getByRole("button", { name: "Remove" });

    const paint = () => remove.evaluate((el) => {
      const s = getComputedStyle(el);
      return s.backgroundImage !== "none" ? s.backgroundImage : s.backgroundColor;
    });
    const resting = await paint();
    await remove.hover();
    await page.waitForTimeout(400);
    const hovered = await paint();

    expect(hovered, "the Remove button lost its colour on hover")
      .toMatch(/gradient|rgb\(2[0-9]{2}, *[0-9]{1,2}, */);
    expect(hovered).not.toBe("rgb(251, 253, 254)");
    expect(resting).toMatch(/gradient/);
  });

  test("adding scrolls to the new band", async ({ page, pageId }) => {
    await openEditor(page, pageId);
    /* A new row goes to the bottom of a full home page, well below the fold. */
    await page.getByRole("button", { name: "Row", exact: true }).click();
    await expect(page.locator(".pe-panel-head p")).toHaveText("New row");

    const added = bands(page, "section").last();
    await expect.poll(async () => {
      const box = await added.boundingBox();
      if (!box) return false;
      const h = page.viewportSize().height;
      /* Visible in the window, not merely present in the document. */
      return box.y < h && box.y + box.height > 0;
    }, { message: "the new band was added off-screen and nothing moved to it" })
      .toBe(true);
  });
});

test.describe("the tab's own words", () => {
  test("the panel offers them when nothing is selected", async ({ page, pageId }) => {
    await openEditor(page, pageId);
    await expect(page.locator(".pe-panel-head h2")).toHaveText("Quick tab");
    /* The panel used to say "click something" and nothing else here. */
    await expect(page.getByRole("textbox", { name: "Shown as", exact: true }))
      .toHaveValue("Quick");
    await expect(page.getByRole("textbox", { name: "Promise", exact: true }))
      .not.toHaveValue("");
  });

  test("changing the promise reaches the shop's feed", async ({ page, api, pageId }) => {
    /* The whole point of these fields: "in minutes" and "2–5 day delivery" are
       what the shop tells a customer it will do, and they were written into the
       storefront's source until now. */
    await openEditor(page, pageId);
    const promise = page.getByRole("textbox", { name: "Promise", exact: true });
    const text = `Delivered in 2 to 5 days ${Date.now()}`;
    await promise.fill(text);
    await expect(page.locator(".pe-chip")).toHaveText(/Saved/, { timeout: 60000 });

    const data = await api.get(`/admin/home/pages/${pageId}/builder?mode=quick`);
    expect(data.mode.tagline).toBe(text);

    await page.reload({ waitUntil: "domcontentloaded" });
    await page.waitForSelector(".pe-band", { state: "attached" });
    await expect(page.getByRole("textbox", { name: "Promise", exact: true }))
      .toHaveValue(text);
  });

  test("switching tabs plays the shop's own effect, naming the tab moved to",
    async ({ page, pageId }) => {
      await openEditor(page, pageId);
      await page.getByRole("tab", { name: "Express" }).click();

      const card = page.locator(".hm-switch-card");
      await expect(card).toBeVisible();
      /* It named the tab being *left* until the card's words were captured at
         click time: the effect swaps `mode` half-way through its own animation. */
      await expect(card.locator("strong")).toHaveText("Express");
      await expect(page.locator(".hm-switch")).toHaveAttribute("data-to", "all");

      await expect(page.locator(".pe-panel-head h2")).toHaveText("Express tab");
    });
});
