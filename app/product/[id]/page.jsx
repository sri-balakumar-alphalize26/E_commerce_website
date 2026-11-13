/* Product details route: /product/<id>.

   The page itself is the client app (ProductRoute). This server wrapper only
   adds the share preview (13 Nov 2026): when the link is pasted in WhatsApp,
   Facebook or a browser tab it shows the product's name, picture and a line
   of description instead of a bare "369 Mart". Read from the same product feed
   the page uses (/369mart/product/<id>); if the shop does not answer in time
   the page still opens, with the site's own title. */
import { headers } from "next/headers";
import { odooFetch } from "@/lib/odoo";
import ProductRoute from "./ProductRoute";

const SITE = "369 Mart";

function feedPath(id) {
  const raw = String(id || "");
  if (/^v\d+$/.test(raw)) return "/369mart/product/" + raw; // a variant: v71
  if (/^\d+$/.test(raw)) return "/369mart/product/" + raw;
  return null;
}

function plain(text, max = 160) {
  const one = String(text || "").replace(/\s+/g, " ").trim();
  return one.length > max ? one.slice(0, max - 1).trimEnd() + "…" : one;
}

export async function generateMetadata({ params }) {
  const { id } = await params;
  const h = await headers();
  const host = h.get("x-forwarded-host") || h.get("host");
  const proto = h.get("x-forwarded-proto") || (host && host.startsWith("localhost") ? "http" : "https");
  const base = host ? new URL(`${proto}://${host}`) : undefined;
  const fallback = { metadataBase: base, title: SITE };

  const path = feedPath(decodeURIComponent(id));
  if (!path) return fallback;
  let p = null;
  try {
    const { status, data } = await odooFetch(path, { signal: AbortSignal.timeout(3000) });
    if (status === 200) p = data?.p || null;
  } catch (e) { /* the page still opens */ }
  if (!p?.name) return fallback;

  const title = `${p.name} · ${SITE}`;
  const description = plain([p.unit, p.description].filter(Boolean).join(" · ")) || "Computer parts and gear. In minutes, or in days.";
  /* WhatsApp's preview is most reliable with a JPG or PNG, so prefer one. */
  const images = (p.images || []).filter(Boolean);
  const picture = images.find((src) => !/\.webp(\?|$)/i.test(src)) || images[0];
  const url = `/product/${encodeURIComponent(decodeURIComponent(id))}`;
  return {
    metadataBase: base,
    title,
    description,
    alternates: { canonical: url },
    openGraph: {
      type: "website", siteName: SITE, url, title, description,
      ...(picture ? { images: [{ url: picture, alt: p.name }] } : {}),
    },
    twitter: { card: picture ? "summary_large_image" : "summary", title, description, ...(picture ? { images: [picture] } : {}) },
  };
}

export default function ProductPage({ params }) {
  return <ProductRoute params={params} />;
}
