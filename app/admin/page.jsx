"use client";
import { useRouter } from "next/navigation";
import AdminApp from "@/components/admin/AdminApp";

export default function AdminRoute() {
  const router = useRouter();
  return <AdminApp section="dashboard" onSection={(k) => history.replaceState(null, "", k === "dashboard" ? "/admin" : `/admin/${k}`)} onExit={() => router.push("/")} />;
}
