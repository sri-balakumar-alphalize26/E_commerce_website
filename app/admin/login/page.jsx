import StaffSignIn from "@/components/admin/StaffSignIn";

/* The staff console's sign-in - the one console page anyone may open
   (middleware.js, AdminGate.jsx). */
export const metadata = { title: "369 Mart · Staff sign in", robots: { index: false, follow: false } };

export default function StaffSignInRoute() {
  return <StaffSignIn />;
}
