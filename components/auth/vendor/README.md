# 369 Mart — Sign in page

`SignIn.jsx` (Next.js client component, no dependencies) + `signin.css` (scoped `.si-*`).
`_preview/preview.html` is the page running with demo responses.

## Flow (email only)
- **Sign in** — email, password (show/hide, Caps Lock warning), keep me signed in
- **Create account** — name, email, password with strength meter, Terms checkbox
- **Forgot password** → **Check your inbox** with 30s resend timer
- **Done** — check mark draws, Continue shopping
- "Continue as guest" under the form

## Install (App Router)
```
components/SignIn.jsx
components/signin.css
app/login/page.jsx
```
```jsx
import SignInPage from "@/components/SignIn";
import "@/components/signin.css";

export default function Page() {
  return (
    <SignInPage
      onEmailSignIn={async (email, password, remember) => ({ ok: true, name: "…" })}
      onCreateAccount={async ({ name, email, password }) => ({ ok: true })}
      onForgotPassword={async (email) => ({ ok: true })}
      onGuest={() => router.push("/checkout")}
      onDone={() => router.push("/")}
    />
  );
}
```
Each async prop returns `{ ok: true }` or `{ ok: false, error: "message shown to the customer" }`.
Every prop has a demo default, so the page runs before the backend is wired (demo: a password under 6 characters fails).
Pass `initialMode="create"` to open on Create account.

Remove the page's big blue "Sign in" band — this layout replaces it; the site header stays.

`SignInCard` and `SignInAside` are also exported if you want the card in a modal or checkout.

## Before going live
- Point `/terms` and `/privacy` links at your real pages.
- `onCreateAccount` can return `{ ok:false, field:"email", error:"An account with this email already exists." }`.
