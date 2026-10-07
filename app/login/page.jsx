"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
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

/* The country picker: default country and list from the shop's database. */
const phoneForm = async () => {
  try {
    const r = await fetch("/api/auth/phone-form");
    return await r.json();
  } catch (e) {
    return { ok: false };
  }
};

export default function LoginRoute() {
  const router = useRouter();
  /* ?add=phone: a signed-in account with no proven number lands here first. */
  const [addPhone, setAddPhone] = useState(false);
  useEffect(() => {
    setAddPhone(new URLSearchParams(window.location.search).get("add") === "phone");
  }, []);
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
        key={addPhone ? "add" : "in"}
        initialMode={addPhone ? "addphone" : "signin"}
        onGuest={() => router.push("/cart")}
        onDone={after}
        onPhoneForm={phoneForm}
        onPhoneStart={(body) => api("phone/start", body)}
        onPhoneVerify={(body) => api("phone/verify", body)}
        onAddPhoneStart={(body) => api("phone/add-start", body)}
        onAddPhoneVerify={(body) => api("phone/add-verify", body)}
        onEmailSignIn={(login, password, remember) => api("login", { login, password, remember })}
        onForgotPassword={(email) => api("forgot", { email })}
      />
    </div>
  );
}
