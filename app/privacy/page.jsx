"use client";
import { useRouter } from "next/navigation";
import Home from "@/components/home/Home";

/* /privacy - the Privacy policy page (sign-in links here). */
export default function InfoRoute() {
  const router = useRouter();
  return <Home initialView="page" initialParam={"privacy"} syncUrl persistCart onSignOut={() => router.push("/login")} />;
}
