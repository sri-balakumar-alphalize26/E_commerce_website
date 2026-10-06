/* /web/assets/<...> -> <ODOO_URL>/web/assets/<...> (see odooPassthrough). */
import { odooPassthrough } from "@/lib/odoo";

export const dynamic = "force-dynamic";

export async function GET(req, ctx) {
  const { path } = await ctx.params;
  return odooPassthrough(req, "/web/assets/" + path.map(encodeURIComponent).join("/"));
}
