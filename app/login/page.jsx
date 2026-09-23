"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import SignInPage from "@/components/signin/SignIn";

/* Every call goes to our own /api/auth/* routes, which talk to Odoo server-side.
   The answers already have the shape the sign-in card expects. */
const api = async (path, body) => {
  try {
    const r = await fetch(`/api/auth/${path}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    return await r.json();
  } catch (e) {
    return { ok: false, error: "Can't reach the server. Try again." };
  }
};

export default function LoginRoute() {
  const router = useRouter();
  const after = () => {
    const next = new URLSearchParams(window.location.search).get("next");
    /* Only a path on this site. "//evil.com" also starts with "/", and a
       browser reads it as another host - as it does "/\evil.com". */
    const safe = next && next.startsWith("/") && !next.startsWith("//") && !next.includes("\\");
    router.push(safe ? next : "/");
  };
  return (
    <div style={{ minHeight: "100vh", background: "#f2f6f9" }}>
      <header className="lg-hdr">
        <Link href="/" className="lg-logo" aria-label="369 Mart home">369<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 18 18 6M9 6h9v9" /></svg>Mart</Link>
      </header>
      <SignInPage
        onGuest={() => router.push("/cart")}
        onDone={after}
        onEmailSignIn={(login, password, remember) => api("login", { login, password, remember })}
        onCreateAccount={(values) => api("signup", values)}
        onForgotPassword={(email) => api("forgot", { email })}
      />
    </div>
  );
}
