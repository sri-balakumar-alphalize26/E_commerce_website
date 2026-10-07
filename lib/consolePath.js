/* The staff console's address, as the browser has it: "/admin" on a machine
   with no secret address set, "/staff-k7p2x9" on one that has (ADMIN_PATH,
   middleware.js). Taken from where the page is rather than written in, so the
   secret word never ends up in the site's code. */
export const consoleBase = () =>
  typeof window === "undefined" ? "/admin" : "/" + (window.location.pathname.split("/")[1] || "admin");

/* consolePath("/orders") -> "/staff-k7p2x9/orders"; consolePath() -> the console home. */
export const consolePath = (rest = "") => consoleBase() + rest;
