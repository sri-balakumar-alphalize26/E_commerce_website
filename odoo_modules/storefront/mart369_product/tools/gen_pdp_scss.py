"""Regenerate static/src/scss/storefront_pdp.scss from the storefront repo.

Run whenever the storefront's product-page styles change, so the phone mock
in 369 Mart > Product Page keeps looking exactly like the real page:

    python tools/gen_pdp_scss.py [path-to-storefront-repo]

Default repo path: C:/Projects/369Mart

Blocks are located by their `/* ---- title ---- */` headers and by brace
balance, never by line number. The home module learned that the hard way: a
two-line shift in the storefront dropped a closing brace and every Odoo page
showed "Style error" until it was regenerated.

Note the product page's styles are spread across four files, not one:
  product.css  the page itself
  browse.css   the breadcrumb, and the pack-size / bought-together blocks
  acx.css      the "your own review" row
`home.css` is NOT copied here - mart369_home's storefront.scss already ships
it, and it carries the --hm-* tokens product.css reads.
"""
import io
import pathlib
import re
import sys
from xml.etree import ElementTree  # noqa: F401  (import kept for parity)

HERE = pathlib.Path(__file__).resolve().parent.parent
OUT = HERE / 'static' / 'src' / 'scss' / 'storefront_pdp.scss'
REPO = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else 'C:/Projects/369Mart')
SRC = REPO / 'components' / 'home'
HEADER_RE = re.compile(r'^\s*/\* -{4,} .+? -{4,} \*/\s*$')


def read(name):
    return io.open(SRC / name, encoding='utf-8').read()


def section(text, title, source):
    """From a `/* ---- title ---- */` header to the line before the next."""
    lines = text.splitlines(keepends=True)
    try:
        start = next(i for i, ln in enumerate(lines)
                     if HEADER_RE.match(ln) and title in ln)
    except StopIteration:
        raise SystemExit('%s: no section header containing %r' % (source, title))
    end = next((i for i in range(start + 1, len(lines)) if HEADER_RE.match(lines[i])),
               len(lines))
    return ''.join(lines[start:end])


def rules(text, prefix, source):
    """Every top-level rule whose selector line starts with `prefix`."""
    lines = text.splitlines(keepends=True)
    out, i = [], 0
    while i < len(lines):
        if lines[i].startswith(prefix):
            depth = 0
            while i < len(lines):
                out.append(lines[i])
                depth += lines[i].count('{') - lines[i].count('}')
                i += 1
                if depth == 0:
                    break
        else:
            i += 1
    if not out:
        raise SystemExit('%s: no rules starting with %r' % (source, prefix))
    return ''.join(out)


product = read('product.css')
browse = read('browse.css')
acx = read('acx.css')

body = (
    '/* ---- components/home/product.css (whole file) ---- */\n' + product +
    '\n/* ---- components/home/browse.css: breadcrumbs ---- */\n'
    + section(browse, 'breadcrumbs', 'browse.css') +
    '\n/* ---- components/home/browse.css: product page pack sizes ---- */\n'
    + section(browse, 'product page: pack sizes', 'browse.css') +
    '\n/* ---- components/home/browse.css: frequently bought together ---- */\n'
    + section(browse, 'product page: frequently bought together', 'browse.css') +
    '\n/* ---- components/home/acx.css: the customer\'s own review row ---- */\n'
    + rules(acx, '.pd-mine', 'acx.css')
)

# The mock is a 390px column inside a wide backend page, so the storefront's
# own phone breakpoints must key off the frame, not the browser window.
body = re.sub(r'@media \(max-width: (\d+px)\)',
              r'@container mart-phone (max-width: \1)', body)
body = body.replace('calc(100vh - 130px)', 'calc(100cqh - 130px)')
body = body.replace('100vw', '100cqw').replace('60vh', '60cqh')

# libsass implements min()/max()/clamp() itself and rejects a calc() inside
# them ("is not a number for `min'"), which blanks the whole Odoo stylesheet.
# Interpolation makes it emit the expression verbatim instead.
body = re.sub(r'(?<![\w-])(min|max|clamp)\(([^()]*\([^()]*\)[^()]*)\)',
              lambda m: '#{"%s(%s)"}' % (m.group(1), m.group(2)), body)

if body.count('{') != body.count('}'):
    raise SystemExit('unbalanced braces in the copied CSS - refusing to write')

HEADER = """// The storefront's product-page styles, copied verbatim so the phone mock
// in the builder looks exactly like the real page. DO NOT hand-edit the
// copied blocks - re-run tools/gen_pdp_scss.py when the storefront changes.
//
// Sources (the storefront repo, components/home/):
//   product.css  whole file
//   browse.css   the "breadcrumbs", "product page: pack sizes" and
//                "product page: frequently bought together" sections
//   acx.css      the .pd-mine rules (the customer's own review)
//
// home.css is deliberately NOT copied: mart369_home/static/src/scss/
// storefront.scss already ships it, and it holds the --hm-* tokens these
// rules read.
//
// Two mechanical rewrites were applied:
//   @media (max-width: N)  ->  @container mart-phone (max-width: N)
//   vw / vh                ->  cqw / cqh
// so the page's own phone breakpoints fire inside the 390px frame.

"""

OVERRIDE = """

/* ==========================================================================
   Builder-only overrides. Kept separate from the copied blocks above.
   ========================================================================== */
.mart-builder .hm-page {
  /* The mock is static: entrance animations would leave things invisible,
     and the sticky gallery would detach from the phone frame. */
  .pd-page, .pd-card, .pd-thumb, .pd-reviews, .pd-deliver { animation: none; }
  .pd-gallery { position: static; }
  .pd-stars-fill { animation: none; }
  /* The toast is fixed to the frame and has nothing to say here. */
  .pd-toast { display: none; }
  /* Show the long description in full - there is no one to click "more". */
  .pd-desc { max-height: none; }
  .pd-desc::after { display: none; }
}

/* The desk editor's wide canvas. The real page lays the gallery and the buy
   card side by side inside `.pd-top`; the mock draws them as plain siblings,
   because each one has to be its own selectable band. Left alone on a canvas
   three times the width of a phone, the gallery's aspect-ratio makes a
   picture the height of the screen. So the page is held to a readable column
   and the stage to a sane size - the only two places the mock's flatter
   structure shows. */
.mart-builder .mart-canvas .hm-page {
  .pd-page { max-width: 880px; margin-inline: auto; }
  .pd-stage { max-width: 420px; margin-inline: auto; }
}
"""

if __name__ == '__main__':
    OUT.write_text(HEADER + body + OVERRIDE, encoding='utf-8', newline='\n')
    text = HEADER + body + OVERRIDE
    print('wrote %s - %d lines, %d container queries'
          % (OUT, len(text.splitlines()), text.count('@container mart-phone')))
