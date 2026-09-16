import "./globals.css";
/* Inter is self-hosted from app/fonts (latin + latin-ext so ₹ renders) — no build-time font download. */

export const metadata = {
  title: "369 Mart",
  description: "Groceries in minutes, everything else in days.",
};

export const viewport = { width: "device-width", initialScale: 1, viewportFit: "cover", themeColor: "#ffffff" };

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
