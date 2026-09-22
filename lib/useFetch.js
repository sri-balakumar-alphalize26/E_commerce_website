"use client";

/* Two hooks, deliberately small. The project has no data library and does not
   need one: the product store already has to be a useSyncExternalStore source,
   and a cache library sitting next to it would be a second cache with its own
   invalidation rules. SWR's defaults would also work against us here --
   revalidating on focus would re-record a search term and re-poll a live
   payment. */

import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError, STALE } from "@/lib/api";

/* Read one thing. `deps` re-fetches; `pollMs` keeps it fresh (paused while the
   tab is hidden, because a UPI approval happens in another app entirely). */
/* `keepLast` is for a screen that polls. Without it a single failed tick sets
   `data` to null, so the list collapses to the error placeholder and the next
   good tick mounts every row again - which replays every staggered entrance
   and reads, to whoever is watching, as the page reloading itself. With it the
   last good read stays on screen and only `error` is set, so the section can
   say it could not reach the shop while still showing what it last knew.

   Opt-in, so that a first load still fails the way every caller expects: there
   is nothing to keep, and a screen that has never loaded must not pretend. */
export function useResource(path, { enabled = true, raw = false, deps = [], pollMs = 0, keepLast = false } = {}) {
  const [state, setState] = useState({ data: null, error: null, loading: enabled, stale: 0 });
  const alive = useRef(true);
  const tick = useRef(0);

  const run = useCallback(async (fresh = false) => {
    if (!enabled || !path) return;
    const mine = ++tick.current;
    try {
      const data = await api(path, { raw, fresh });
      if (alive.current && mine === tick.current) setState({ data, error: null, loading: false, stale: data?.[STALE] || 0 });
    } catch (e) {
      if (alive.current && mine === tick.current) {
        setState((s) => (keepLast && s.data
          ? { ...s, error: e, loading: false }
          : { data: null, error: e, loading: false, stale: 0 }));
      }
    }
  }, [path, enabled, raw, keepLast]);

  useEffect(() => {
    alive.current = true;
    setState((s) => ({ ...s, loading: enabled }));
    run();
    return () => { alive.current = false; };
  }, [run, ...deps]); // eslint-disable-line

  useEffect(() => {
    if (!pollMs || !enabled) return;
    let id = null;
    const start = () => { stop(); id = setInterval(() => run(true), pollMs); };
    const stop = () => { if (id) clearInterval(id); id = null; };
    const onVisible = () => (document.visibilityState === "hidden" ? stop() : (run(true), start()));
    if (document.visibilityState !== "hidden") start();
    document.addEventListener("visibilitychange", onVisible);
    return () => { stop(); document.removeEventListener("visibilitychange", onVisible); };
  }, [pollMs, enabled, run]);

  return { ...state, reload: () => run(true) };
}

/* Write one thing. Keeps the server's message and its `field` so a form can put
   the error under the control the server named. */
export function useAction() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const run = useCallback(async (fn) => {
    setBusy(true); setError(null);
    try {
      return await fn();
    } catch (e) {
      setError(e instanceof ApiError ? e : new ApiError(e?.message || "Something went wrong."));
      return null;
    } finally {
      setBusy(false);
    }
  }, []);
  return { run, busy, error, clearError: () => setError(null) };
}
