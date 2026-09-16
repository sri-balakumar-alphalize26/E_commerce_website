"use client";
import { useRouter } from "next/navigation";
import Home from "@/components/home/Home";

export default function AccountRoute() {
  const router = useRouter();
  return <Home initialView="account" syncUrl persistCart onSignOut={() => router.push("/login")} />;
}
