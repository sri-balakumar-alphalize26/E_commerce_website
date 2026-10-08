"use client";
import { useRouter } from "next/navigation";
import Home from "@/components/home/Home";

/* /terms - the Terms of use page (sign-in links here). */
export default function InfoRoute() {
  const router = useRouter();
  return <Home initialView="page" initialParam={"terms"} syncUrl persistCart onSignOut={() => router.push("/login")} />;
}
