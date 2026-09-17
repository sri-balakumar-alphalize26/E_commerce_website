"use client";
import { useRouter } from "next/navigation";
import Home from "@/components/home/Home";

/* Any unknown URL — animated 404 inside the normal store shell */
export default function NotFound() {
  const router = useRouter();
  return <Home initialView="notfound" syncUrl persistCart onSignOut={() => router.push("/login")} />;
}
