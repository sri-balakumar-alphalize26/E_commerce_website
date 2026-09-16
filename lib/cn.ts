/** Tiny class-name joiner — no dependency needed for this. */
export function cn(...parts: Array<string | false | null | undefined>) {
  return parts.filter(Boolean).join(' ')
}
