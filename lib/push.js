"use client";

/* Pop-ups when the shop is closed (Web Push), the page's side.

   Turning them on: the browser asks the customer, a worker (public/sw.js) is
   installed to receive them, and the address the browser gives is sent to the
   shop under the signed-in customer (Odoo, mart369_account/models/push.py).

   Browsers that cannot do it - older ones, and iPhone Safari unless the shop
   has been added to the Home Screen - answer "unsupported", and the page
   simply does not offer it. */

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";

export const pushSupported = () =>
  typeof window !== "undefined" && window.isSecureContext &&
  "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;

const bytes = (b64) => {
  const raw = atob(b64.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((b64.length + 3) % 4));
  return Uint8Array.from(raw, (c) => c.charCodeAt(0));
};

const sameKey = (sub, key) => {
  const had = sub.options?.applicationServerKey;
  if (!had) return true; /* the browser does not say; trust it */
  const a = new Uint8Array(had), b = bytes(key);
  return a.length === b.length && a.every((x, i) => x === b[i]);
};

async function registration() {
  return (await navigator.serviceWorker.getRegistration("/")) || null;
}

/* "unsupported" | "denied" | "on" | "off" */
export async function pushState() {
  if (!pushSupported()) return "unsupported";
  if (Notification.permission === "denied") return "denied";
  const reg = await registration();
  const sub = reg && (await reg.pushManager.getSubscription());
  return sub && Notification.permission === "granted" ? "on" : "off";
}

export async function enablePush() {
  if (!pushSupported()) return "unsupported";
  const permission = await Notification.requestPermission();
  if (permission !== "granted") return permission === "denied" ? "denied" : "off";
  const reg = await navigator.serviceWorker.register("/sw.js");
  await navigator.serviceWorker.ready;
  const { key } = await api("/push/key", { fresh: true });
  let sub = await reg.pushManager.getSubscription();
  if (sub && !sameKey(sub, key)) { await sub.unsubscribe(); sub = null; }
  sub = sub || (await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: bytes(key) }));
  await api("/push/subscribe", { method: "POST", body: sub.toJSON() });
  return "on";
}

export async function disablePush() {
  const reg = pushSupported() ? await registration() : null;
  const sub = reg && (await reg.pushManager.getSubscription());
  if (sub) {
    await api("/push/unsubscribe", { method: "POST", body: { endpoint: sub.endpoint } }).catch(() => {});
    await sub.unsubscribe().catch(() => {});
  }
  return pushSupported() ? "off" : "unsupported";
}

export const testPush = () => api("/push/test", { method: "POST" });

/* Tell the shop again which customer this browser belongs to - once a visit,
   while signed in. A shared computer signed into by somebody else moves to
   them, and a browser the shop forgot is put back. */
let synced = false;
async function resync() {
  if (synced) return;
  synced = true;
  try {
    const reg = await registration();
    const sub = reg && (await reg.pushManager.getSubscription());
    if (sub && Notification.permission === "granted") await api("/push/subscribe", { method: "POST", body: sub.toJSON() });
  } catch (e) {
    synced = false;
  }
}

/* The switch: where pop-ups are for this browser, and the two ways to move it. */
export function usePush(signedIn = true) {
  const [state, setState] = useState(null); /* null until the browser has answered */
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    let live = true;
    pushState().then((s) => {
      if (!live) return;
      setState(s);
      if (s === "on" && signedIn) resync();
    }).catch(() => live && setState("unsupported"));
    return () => { live = false; };
  }, [signedIn]);

  const act = useCallback(async (fn) => {
    setBusy(true); setError(null);
    try {
      setState(await fn());
    } catch (e) {
      setError(e?.message || "Pop-ups could not be changed. Please try again.");
      setState(await pushState().catch(() => "unsupported"));
    } finally {
      setBusy(false);
    }
  }, []);

  return {
    state, busy, error,
    turnOn: () => act(enablePush),
    turnOff: () => act(disablePush),
  };
}
