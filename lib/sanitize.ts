import 'server-only'
import sanitizeHtml from 'sanitize-html'

/**
 * Sanitises product description HTML.
 *
 * `import 'server-only'` is the guard that matters: this must never run in a
 * client component. Sanitising in the browser means the unsanitised string
 * already travelled there in the RSC payload, so anything that reads it
 * before the sanitiser does -- or any bug that renders it directly -- is an
 * XSS hole. Keeping it server-side makes that a build error rather than a
 * code-review question.
 *
 * The allowlist is deliberately small. A description is prose and a spec
 * list; it has no business carrying scripts, styles, iframes or forms.
 */
const OPTIONS: sanitizeHtml.IOptions = {
  allowedTags: ['p', 'br', 'strong', 'em', 'b', 'i', 'ul', 'ol', 'li', 'h3', 'h4', 'a'],
  allowedAttributes: { a: ['href', 'title'] },
  allowedSchemes: ['http', 'https', 'mailto'],
  transformTags: {
    // Any link in supplier-authored copy is untrusted: open it away from the
    // session and give search engines nothing.
    a: sanitizeHtml.simpleTransform('a', {
      rel: 'noopener noreferrer nofollow',
      target: '_blank',
    }),
  },
}

export function sanitizeDescription(html: string) {
  return sanitizeHtml(html, OPTIONS)
}
