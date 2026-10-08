/* 369 Mart - the browser's side of pop-ups (Web Push).

   The shop sends an encrypted message when an order moves (Odoo,
   mart369_account/models/push.py); the browser wakes this worker with it, even
   with every 369 Mart tab closed, and this shows it. Tapping it opens the
   order and marks the bell's row read.

   With the shop open and in front of the customer, a system pop-up on top of
   the page would be noise: the page is told instead, and its bell updates and
   shows its own card (components/home/Bell.jsx). */

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));

self.addEventListener("push", (event) => {
  let note = {};
  try {
    note = event.data ? event.data.json() : {};
  } catch (e) {
    note = { body: event.data ? event.data.text() : "" };
  }
  event.waitUntil((async () => {
    const tabs = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    tabs.forEach((tab) => tab.postMessage({ type: "369mart:push", note }));
    if (tabs.some((tab) => tab.visibilityState === "visible" && tab.focused)) return;
    await self.registration.showNotification(note.title || "369 Mart", {
      body: note.body || "",
      icon: "/brand/369mart-icon.png",
      tag: note.id || undefined,
      renotify: !!note.id,
      data: { url: note.url || "/", id: note.id || null },
    });
  })());
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const { url = "/", id = null } = event.notification.data || {};
  event.waitUntil((async () => {
    if (id) {
      /* Same-origin, so the customer's sign-in cookie goes with it. */
      fetch("/api/mart/notifications/read", {
        method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ids: [id] }),
      }).catch(() => {});
    }
    const target = new URL(url, self.location.origin).href;
    const tabs = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    const tab = tabs.find((t) => new URL(t.url).origin === self.location.origin);
    if (tab) {
      await tab.focus();
      if (tab.navigate) await tab.navigate(target).catch(() => {});
      return;
    }
    await self.clients.openWindow(target);
  })());
});

/* The browser replaced the address it gave the shop (it does, now and then):
   sign the new one up, as the same customer, so pop-ups keep coming. */
self.addEventListener("pushsubscriptionchange", (event) => {
  event.waitUntil((async () => {
    try {
      const old = event.oldSubscription;
      const res = await fetch("/api/mart/push/key", { credentials: "same-origin" });
      const { key } = await res.json();
      const raw = atob(key.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((key.length + 3) % 4));
      const sub = event.newSubscription || await self.registration.pushManager.subscribe({
        userVisibleOnly: true, applicationServerKey: Uint8Array.from(raw, (c) => c.charCodeAt(0)),
      });
      const post = (path, body) => fetch("/api/mart/push/" + path, {
        method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
      });
      if (old) await post("unsubscribe", { endpoint: old.endpoint });
      await post("subscribe", sub.toJSON());
    } catch (e) {
      /* Signed out, or offline: the page signs it up again next visit. */
    }
  })());
});
