'use client'

import { useRouter } from 'next/navigation'
import SignInPage from '@/components/auth/vendor/SignIn'
import {
  DEMO_EMAIL,
  DEMO_PASSWORD,
  DEMO_PROFILE,
  isDemoLogin,
  isValidEmail,
  MIN_PASSWORD,
} from '@/lib/session'
import { signIn } from '@/lib/session-store'
import '@/components/auth/vendor/signin.css'
import '@/components/auth/vendor/signin.brand.css'

/**
 * Sign in, rendering the vendored design.
 *
 * Each callback returns `{ ok }` or `{ ok, error, field }` and the design
 * handles the rest -- the shake, the inline message, the mode transitions.
 * Nothing inside components/auth/vendor knows about the session store.
 *
 * The validation rules here are the ones Odoo's /api/register enforces: a
 * valid-looking email and a six-character minimum. Matching them now means
 * connecting real auth later replaces these four functions and nothing else,
 * and no returning customer meets a rule they did not have to satisfy before.
 */
export default function LoginRoute() {
  const router = useRouter()

  return (
    <>
      <SignInPage
        onEmailSignIn={async (email: string, password: string) => {
          // Checked before validation, because the demo pair is deliberately
          // not a valid email and deliberately too short -- the rules below
          // would reject it, which is exactly what keeps it unreachable by
          // accident.
          if (isDemoLogin(email, password)) {
            await signIn(DEMO_PROFILE)
            return { ok: true, name: DEMO_PROFILE.name }
          }
          if (!isValidEmail(email)) {
            return { ok: false, field: 'email', error: 'Enter a valid email address.' }
          }
          if (password.length < MIN_PASSWORD) {
            return {
              ok: false,
              field: 'password',
              error: `Your password is at least ${MIN_PASSWORD} characters.`,
            }
          }
          // There is no credential to check against yet. The profile is stored
          // on this device so the header, sidebar and Sign out are real state
          // rather than decoration; the password is deliberately not kept.
          const name = email.split('@')[0]
          await signIn({ name, email: email.trim(), phone: '' })
          return { ok: true, name }
        }}

        onCreateAccount={async ({
          name,
          email,
          password,
        }: {
          name: string
          email: string
          password: string
        }) => {
          if (name.trim().length < 2) {
            return { ok: false, field: 'name', error: 'Please enter your name.' }
          }
          if (!isValidEmail(email)) {
            return { ok: false, field: 'email', error: 'Enter a valid email address.' }
          }
          if (password.length < MIN_PASSWORD) {
            return {
              ok: false,
              field: 'password',
              error: `Choose a password of at least ${MIN_PASSWORD} characters.`,
            }
          }
          await signIn({ name: name.trim(), email: email.trim(), phone: '' })
          return { ok: true }
        }}

        /*
         * Reports honestly instead of succeeding.
         *
         * The design's happy path is a "Check your inbox" screen with a resend
         * timer. Wiring that to a local stub would be the most convincing lie
         * in either of these layouts -- someone would sit waiting for an email
         * that was never sent, and there is no mail service here to send one.
         * Returning an error keeps them on the form, where they can still sign
         * in.
         */
        onForgotPassword={async () => ({
          ok: false,
          error: 'Password reset needs the store backend, which is not connected yet.',
        })}

        onGuest={() => router.push('/')}
        onDone={() => router.push('/account')}
      />

      {/*
        The demo credential, printed rather than hidden.

        A sign-in form with no backend behind it gives a first-time visitor
        nothing to try, and one that quietly accepts anything is worse --
        it looks broken the moment someone tests it with a wrong password.
        Saying what works, and that nothing is being checked, is the honest
        version of both.

        Rendered here rather than inside the vendored design, which is kept
        byte-identical to its archive.
      */}
      <p className="text-slate-muted mx-auto max-w-[1080px] px-4 pb-10 text-center text-xs">
        Demo build — sign in with <b className="text-ink font-bold">{DEMO_EMAIL}</b> /{' '}
        <b className="text-ink font-bold">{DEMO_PASSWORD}</b>, or any email address and a password
        of {MIN_PASSWORD} characters. No credential is checked, and no password is stored.
      </p>
    </>
  )
}
