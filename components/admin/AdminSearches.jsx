"use client";
/* ==========================================================================
   369 Mart admin — Searches

   The one screen that answers a question nothing else in the console can:
   **what did customers ask for that the shop does not sell?**

   Every search in the app is already counted on `mart369.search.term`. The
   rows with no results are the useful half — somebody wanted something, the
   search came back empty, and they left. Those sit at the top of their own
   tab with a mark down the edge.

   Only one thing here can be written: whether a term may be offered back to
   shoppers as a suggestion. What was searched for, how often, how many
   results it found and when are counts of things that really happened — a
   screen that could edit them could make the catalogue's own gaps disappear
   by typing over them.
   ========================================================================== */
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { useAction, useResource } from "@/lib/useFetch";
import { Empty, Icon, Search, Switch, Tabs } from "./AdminUI";
import { dateTime, since } from "./format";

export function SearchesSection({ flash }) {
  const [tab, setTab] = useState("all");
  /* What is typed and what has been asked for, kept apart the way Orders and
     Referrals keep them: without the gap every keystroke is a request, and on
     a slow connection the answers come back out of order. */
  const [term, setTerm] = useState("");
  const [q, setQ] = useState("");

  useEffect(() => {
    const id = setTimeout(() => setQ(term.trim()), 300);
    return () => clearTimeout(id);
  }, [term]);

  const path = useMemo(() => {
    const p = new URLSearchParams();
    if (tab !== "all") p.set("tab", tab);
    if (q) p.set("q", q);
    const qs = p.toString();
    return "/admin/searches" + (qs ? `?${qs}` : "");
  }, [tab, q]);

  const { data, loading, error, reload } = useResource(path);
  const act = useAction();

  const rows = data?.rows || [];
  const counts = data?.counts || {};
  const tiles = data?.tiles || {};

  /* Read-after-write, as everywhere else in this console: which tab a term
     now belongs to is the server's answer, and a row toggled locally would
     sit in a tab it no longer matches until the next reload. */
  const run = (fn, ok) =>
    act.run(async () => {
      await fn();
      api.invalidate("/admin/searches");
      await reload();
      if (ok) flash?.(ok);
      return true;
    }).then((r) => {
      if (r === null) flash?.(act.error?.message || "That did not work.", "bad");
      return r;
    });

  const setTrending = (r, on) =>
    run(
      () => api(`/admin/searches/${r.id}`, { method: "PATCH", body: { trending: on } }),
      on ? `"${r.term}" can be suggested again` : `"${r.term}" will not be suggested`
    );

  const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;

  return (
    <div className="ad-stack">
      <section className="ad-mini-stats">
        <span><small>Searches</small><b>{tiles.searches ?? 0}</b></span>
        <span><small>Different terms</small><b>{tiles.terms ?? 0}</b></span>
        <span className={tiles.empty ? "ad-bad" : ""}>
          <small>Found nothing</small><b>{tiles.empty ?? 0}</b>
        </span>
        <span><small>Not suggested</small><b>{tiles.blocked ?? 0}</b></span>
      </section>

      {/* Said once, above everything: a number on a tile does not ask for
          anything to be done about it, and this one should. */}
      {!!tiles.empty && (
        <p className="ad-hint ad-gap-note">
          <Icon n="info" size={14} />
          <span>
            <b>{plural(tiles.empty, "term", "terms")}</b> found nothing, over{" "}
            <b>{plural(tiles.empty_searches ?? 0, "search", "searches")}</b>. That is
            what customers wanted and the shop does not stock.
          </span>
        </p>
      )}

      <section className="ad-card">
        <div className="ad-toolbar">
          <Tabs value={tab} onChange={setTab} tabs={[
            ["all", "All", counts.all ?? 0],
            ["popular", "Most searched", counts.popular ?? 0],
            ["empty", "Found nothing", counts.empty ?? 0],
            ["blocked", "Not suggested", counts.blocked ?? 0],
          ]} />
          <div className="ad-toolbar-right">
            <Search value={term} onChange={setTerm} placeholder="A word somebody searched for" />
          </div>
        </div>

        {error && (
          <Empty icon="info" title="We could not reach the shop" text={error.message}
            action="Try again" onAction={reload} />
        )}
        {loading && !rows.length && !error && (
          <Empty icon="search" title="Loading…" text="Fetching searches." />
        )}
        {!error && !loading && !rows.length && (
          <Empty icon="search"
            title={tab === "empty" ? "Every search found something" : "No term here"}
            text={tab === "empty"
              ? "That is the good version of this tab being empty."
              : q || tab !== "all"
                ? "Nothing matches that. Try another tab, or clear the search."
                : "Every search in the app is counted here as it happens."} />
        )}

        {!error && !!rows.length && (
          <ul className="ad-terms">
            {rows.map((r, i) => (
              <li key={r.id} className={r.results ? "" : "ad-term-gap"} style={{ "--i": i }}>
                <div className="ad-term-body">
                  <div className="ad-term-top">
                    <b>{r.term}</b>
                    {!r.results && <span className="ad-pill ad-t-red"><i />Found nothing</span>}
                  </div>
                  <small>
                    searched <b>{r.hits}</b> {r.hits === 1 ? "time" : "times"}
                    {" · "}
                    {r.results
                      ? `${plural(r.results, "result", "results")} last time`
                      : "no results last time"}
                    {r.at ? <> {" · "}<span title={dateTime(r.at)}>{since(r.at)}</span></> : null}
                  </small>
                </div>
                <Switch on={r.trending} label="Suggest to shoppers"
                  onChange={(on) => setTrending(r, on)} />
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
