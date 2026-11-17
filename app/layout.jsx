import "./globals.css";
/* Inter is self-hosted from app/fonts (latin + latin-ext so ₹ renders) — no build-time font download. */

export const metadata = {
  title: "369 Mart",
  description: "Computer parts and gear. In minutes, or in days.",
};

export const viewport = { width: "device-width", initialScale: 1, viewportFit: "cover", themeColor: "#ffffff" };

/* The image server (IMAGE_SERVER_URL in .env.local), when there is one: the
   browser starts connecting to it while the page loads, so the first product
   picture on a phone does not wait for that. Not set = nothing added. */
function imageHost() {
  try {
    const u = new URL(process.env.IMAGE_SERVER_URL || "");
    return u.protocol === "https:" || u.protocol === "http:" ? u.origin : "";
  } catch {
    return "";
  }
}

export default function RootLayout({ children }) {
  const host = imageHost();
  return (
    <html lang="en">
      {host ? (
        <head>
          <link rel="preconnect" href={host} />
          <link rel="dns-prefetch" href={host} />
        </head>
      ) : null}
      <body>{children}</body>
    </html>
  );
}
