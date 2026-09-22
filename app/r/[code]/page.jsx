/* An invite link.
 *
 * `/369mart/referrals` hands a shopper `369mart.in/r/<their code>`, which had
 * nowhere to land - so an invite could be sent but never followed, and the
 * referral it was meant to start could never happen.
 *
 * The code has to survive the hop to sign-up, so it is remembered before the
 * redirect rather than carried in the URL: a shopper often browses first and
 * signs up later, and a query string does not last that long.
 */
"use client";

import { useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import { rememberReferral } from "@/lib/referral";

export default function ReferralLanding() {
  const { code } = useParams();
  const router = useRouter();

  useEffect(() => {
    rememberReferral(code);
    /* Replace, not push: the back button should take them where they came
       from, not round this redirect again. */
    router.replace("/login?new=1");
  }, [code, router]);

  return (
    <main className="hm-page" style={{ padding: "48px 20px", textAlign: "center" }}>
      <p>Taking you to sign up…</p>
    </main>
  );
}
