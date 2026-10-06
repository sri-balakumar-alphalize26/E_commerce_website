/* /web/image/<...> -> <ODOO_URL>/web/image/<...> (see odooPassthrough). */
import { odooPassthrough } from "@/lib/odoo";

export const dynamic = "force-dynamic";

export async function GET(req, ctx) {
  const { path } = await ctx.params;
  return odooPassthrough(req, "/web/image/" + path.map(encodeURIComponent).join("/"));
}
