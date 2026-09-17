"use client";
import { useRouter } from "next/navigation";
import Home from "@/components/home/Home";

/* /buy-again — items from past orders (header clock icon) */
export default function BuyAgainRoute() {
  const router = useRouter();
  return <Home initialView="buyagain" syncUrl persistCart onSignOut={() => router.push("/login")} />;
}
