"use client";
import { use } from "react";
import { useRouter } from "next/navigation";
import Home from "@/components/home/Home";

/* /order/<id> — payment success with the printed receipt */
export default function OrderRoute({ params }) {
  const { id } = use(params);
  const router = useRouter();
  return <Home initialView="order" initialParam={decodeURIComponent(id)} syncUrl persistCart onSignOut={() => router.push("/login")} />;
}
