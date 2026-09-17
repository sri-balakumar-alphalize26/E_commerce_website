"use client";
import { use } from "react";
import { useRouter } from "next/navigation";
import Home from "@/components/home/Home";

/* /track/<id> — live order status, rider map, cancel, rate, return, help */
export default function TrackRoute({ params }) {
  const { id } = use(params);
  const router = useRouter();
  return <Home initialView="track" initialParam={decodeURIComponent(id)} syncUrl persistCart onSignOut={() => router.push("/login")} />;
}
