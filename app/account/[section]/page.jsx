"use client";
import { use } from "react";
import { useRouter } from "next/navigation";
import Home from "@/components/home/Home";

/* /account/<section> — wallet, payments, rewards, reviews, notifications, refer, orders, … */
export default function AccountSectionRoute({ params }) {
  const { section } = use(params);
  const router = useRouter();
  return <Home initialView="account" initialParam={decodeURIComponent(section)} syncUrl persistCart onSignOut={() => router.push("/login")} />;
}
