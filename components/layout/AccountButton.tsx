'use client'

import Link from 'next/link'
import { UserRound } from 'lucide-react'
import { initialsOf } from '@/lib/session'
import { useSession } from '@/lib/use-session'

/**
 * The account entry point.
 *
 * Signed out it is a person glyph linking to sign-in; signed in it becomes
 * the customer's initials linking to the account. Both destinations exist,
 * which is the whole reason this is back -- it was removed earlier precisely
 * because /account was a hard 404 from permanent chrome.
 *
 * The server cannot know about a device-local session, so the first paint is
 * always the signed-out face and the initials appear after hydration.
 */
export default function AccountButton() {
  const { profile, signedIn } = useSession()

  return (
    <Link
      href={signedIn ? '/account' : '/login'}
      aria-label={signedIn ? `Account: ${profile?.name}` : 'Sign in'}
      className="chip-on-brand inline-flex size-9 shrink-0 items-center justify-center rounded-pill text-white transition-colors"
    >
      {signedIn && profile ? (
        <span className="text-[13px] font-extrabold">{initialsOf(profile.name)}</span>
      ) : (
        <UserRound className="size-[18px]" aria-hidden />
      )}
    </Link>
  )
}
