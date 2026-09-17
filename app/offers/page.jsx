"use client";
import { useRouter } from "next/navigation";
import Home from "@/components/home/Home";

/* /offers — deal countdown, coupons, top deals (header % icon) */
export default function OffersRoute() {
  const router = useRouter();
  return <Home initialView="offers" syncUrl persistCart onSignOut={() => router.push("/login")} />;
}
