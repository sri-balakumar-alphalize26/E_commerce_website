/**
 * Always draw the top bar from the server, never from the browser's copy.
 *
 * Odoo 19's menu service keeps the menus in localStorage ("webclient_menus")
 * and draws that copy first, fetching the real ones in the background. The
 * copy is only thrown away when the registry hash changes - and moving menus
 * under new headings does not change it. So a browser that had the menus
 * before the 369 Mart bar was regrouped kept showing the old flat row of
 * entries (Orders, Returns, Support, ...) until somebody reloaded, and it
 * came back whenever that stale copy was the one on hand.
 *
 * Runs when the bundle is evaluated, which is before the web client starts
 * its services, so the menu service finds nothing stored and fetches. That is
 * one small request per page load, in exchange for a bar that is always the
 * one on the server.
 */
try {
    window.localStorage.removeItem("webclient_menus");
    window.localStorage.removeItem("webclient_menus_version");
} catch {
    // Private windows and blocked storage: nothing was stored to go stale.
}
