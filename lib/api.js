/* The storefront's side of the proxy. Every screen reads the backend through
   this, so the awkward parts of the contract are handled once, here. */

export class ApiError extends Error {
  constructor(message, { status = 0, field = null, data = null } = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.field = field;   /* {ok:false, error, field} -> inline under that control */
    this.data = data;
  }
}

const OFFLINE = "Can't reach the store. Try again in a moment.";

/* How old an answer is, in seconds, when the proxy served its kept copy because
   Odoo was unreachable. Deliberately a Symbol and not a field: the home payload
   is walked with Object.values(), and a stray number sitting among the modes
   would be read as one and crash. Object.values() does not see Symbol keys. */
export const STALE = Symbol("mart.staleAge");

function markStale(data, res) {
  const age = res.headers.get("x-mart-stale-age");
  if (!age || !data || typeof data !== "object") return data;
  try {
    Object.defineProperty(data, STALE, { value: Number(age), enumerable: false });
  } catch (e) { /* frozen body: not worth failing a page over */ }
  return data;
}

/* GET results are held briefly and shared. Two reasons this is not an
   optimisation:
   - /search?q= records the term it was asked for, and React's strict mode runs
     effects twice in development, so every search would be counted twice.
   - the proxy answers no-store, so the browser cache cannot help at all. */
const cache = new Map(); /* url -> { at, promise } */
const TTL = 60 * 1000;

export function invalidate(prefix = "") {
  for (const url of [...cache.keys()]) if (url.startsWith("/api/mart" + prefix)) cache.delete(url);
}

async function send(url, { method, body, raw }) {
  let res, data;
  try {
    res = await fetch(url, {
      method,
      credentials: "same-origin",
      cache: "no-store",
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch (e) {
    if (raw) return { ok: false, error: OFFLINE, offline: true };
    throw new ApiError(OFFLINE, { status: 0 });
  }

  try { data = await res.json(); } catch (e) { data = null; }
  markStale(data, res);

  if (res.status === 401 && typeof window !== "undefined") {
    /* One event, so the shell decides what a lost session means for the view
       the shopper is actually on. A redirect from here would fire mid-payment. */
    window.dispatchEvent(new CustomEvent("369mart:signedout"));
  }

  /* raw: the caller wants the body whatever it says. Three routes answer
     HTTP 200 on a logical failure -- /serviceability, /payment/status/<ref>
     and everything under /support -- and one of them is rendered directly by
     LocationPicker. Throwing on those would be wrong. */
  if (raw) return data ?? { ok: false, error: OFFLINE };

  /* Not every failure carries ok:false -- /product/<id> answers a bare
     {error:'not_found', id} with a 404 -- so the status matters too. */
  const failed = data?.ok === false || (!res.ok && data?.ok !== true);
  if (failed) {
    throw new ApiError(data?.error || OFFLINE, { status: res.status, field: data?.field ?? null, data });
  }
  return data;
}

export function api(path, { method = "GET", body, raw = false, fresh = false } = {}) {
  const url = "/api/mart" + path;
  if (method !== "GET") {
    return send(url, { method, body, raw });
  }
  const hit = cache.get(url);
  if (!fresh && hit && Date.now() - hit.at < TTL) return hit.promise;
  const promise = send(url, { method, raw }).catch((e) => {
    cache.delete(url); /* never cache a failure */
    throw e;
  });
  cache.set(url, { at: Date.now(), promise });
  return promise;
}

api.invalidate = invalidate;
api.ApiError = ApiError;
