"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import SignInPage from "@/components/signin/SignIn";

export default function LoginRoute() {
  const router = useRouter();
  return (
    <div style={{ minHeight: "100vh", background: "#f2f6f9" }}>
      <header className="lg-hdr">
        <Link href="/" className="lg-logo" aria-label="369 Mart home">369<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 18 18 6M9 6h9v9" /></svg>Mart</Link>
      </header>
      <SignInPage
        onGuest={() => router.push("/cart")}
        onDone={() => router.push("/")}
        /* Wire to your backend — each returns { ok } or { ok:false, error } */
        // onEmailSignIn={async (email, password, remember) => fetch("/api/auth/login", …)}
        // onCreateAccount={async ({ name, email, password }) => …}
        // onForgotPassword={async (email) => …}
      />
    </div>
  );
}
