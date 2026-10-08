"use client";
import { useRouter } from "next/navigation";
import Home from "@/components/home/Home";

/* /cancellation-policy - Cancellations & returns (cart and product page link here). */
export default function InfoRoute() {
  const router = useRouter();
  return <Home initialView="page" initialParam={"cancellation-policy"} syncUrl persistCart onSignOut={() => router.push("/login")} />;
}
