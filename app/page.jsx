"use client";
import { useRouter } from "next/navigation";
import Home from "@/components/home/Home";

export default function Page() {
  const router = useRouter();
  return <Home syncUrl persistCart onSignOut={() => router.push("/login")} />;
}
