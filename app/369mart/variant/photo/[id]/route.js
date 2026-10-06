/* A product variant's extra photos (its Variant images tab), which /web/image
   cannot serve to a shopper. -> <ODOO_URL>/369mart/variant/photo/<id> */
import { odooPassthrough } from "@/lib/odoo";

export const dynamic = "force-dynamic";

export async function GET(req, ctx) {
  const { id } = await ctx.params;
  return odooPassthrough(req, "/369mart/variant/photo/" + encodeURIComponent(id));
}
