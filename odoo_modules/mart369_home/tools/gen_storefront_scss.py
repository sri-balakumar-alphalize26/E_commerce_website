"""Regenerate static/src/scss/storefront.scss from the storefront repo.

Run whenever the storefront's home stylesheets change, so the builder's
phone mock keeps looking exactly like the app:

    python tools/gen_storefront_scss.py [path-to-storefront-repo]

Default repo path: C:/Projects/369Mart

Blocks are located by their section-header comments and by brace balance,
never by line number: the storefront is edited constantly and a line range
that was one complete block yesterday is half a block today.
"""
import io
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent.parent
OUT = HERE / 'static' / 'src' / 'scss' / 'storefront.scss'
REPO = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else 'C:/Projects/369Mart')
SRC = REPO / 'components' / 'home'
HEADER_RE = re.compile(r'^/\* -{4,} .+? -{4,} \*/\s*$')


def read(name):
    return io.open(SRC / name, encoding='utf-8').read()


def section(text, title):
    """From the `/* ---- title ---- */` header line to the line before the
    next such header (or the end of the file)."""
    lines = text.splitlines(keepends=True)
    start = next(i for i, ln in enumerate(lines)
                 if HEADER_RE.match(ln) and title in ln)
    end = next((i for i in range(start + 1, len(lines)) if HEADER_RE.match(lines[i])),
               len(lines))
    return ''.join(lines[start:end])


def block(text, opener, must_contain):
    """The first brace-balanced block whose opening line starts with `opener`
    and whose body mentions `must_contain`."""
    lines = text.splitlines(keepends=True)
    for i, ln in enumerate(lines):
        if not ln.startswith(opener):
            continue
        depth, out = 0, []
        for ln2 in lines[i:]:
            out.append(ln2)
            depth += ln2.count('{') - ln2.count('}')
            if depth == 0:
                break
        body = ''.join(out)
        if must_contain in body:
            return body
    raise SystemExit('block %r containing %r not found' % (opener, must_contain))


home = read('home.css')
gallery = section(read('extras.css'), 'product image gallery')
cartfx = read('cartfx.css')
pill = section(cartfx, 'floating pill')
pill_phone = block(cartfx, '@media (max-width: 560px)', '.mc-pill')

body = (
    "/* ---- components/home/home.css (whole file) ---- */\n" + home +
    "\n/* ---- components/home/extras.css: product image gallery ---- */\n" + gallery +
    "\n/* ---- components/home/cartfx.css: floating pill (the cart bar the app really renders) ---- */\n" + pill +
    "\n/* ---- components/home/cartfx.css: the pill on phones ---- */\n" + pill_phone
)

# The mock is a 390px column inside a wide backend page. Viewport media
# queries would never match, so they become container queries keyed on the
# phone frame, and viewport units become container units.
body = re.sub(r'@media \(max-width: (\d+px)\)', r'@container mart-phone (max-width: \1)', body)
body = body.replace('2.1vw', '2.1cqw').replace('100vw', '100cqw')
body = body.replace('min-height: 100vh;', 'min-height: 100%;')

# libsass implements min()/max()/clamp() itself rather than passing them to
# the browser, and then rejects two things CSS is perfectly happy with: a
# calc() inside one ("is not a number for `min'"), and mixed units
# ("Incompatible units: 'px' and 'cqw'"). Either one fails the whole
# web.assets_web bundle and every Odoo page shows "Style error".
#
# home.css has no offender today - its min() calls take a var(), which passes
# through untouched. But cartfx.css:75 is `width: min(380px, calc(100vw -
# 32px))`, sitting just outside the section sliced above, and the 100vw ->
# 100cqw rewrite would turn it into exactly the first failure. Interpolating
# hands the whole expression to the browser, which is what we wanted anyway.
# The lookbehind keeps `min-height:` / `max-width:` out of it.
body = re.sub(r'(?<![\w-])(min|max|clamp)\(((?:[^()]|\([^()]*\))*)\)',
              lambda m: '#{"%s(%s)"}' % (m.group(1), m.group(2)), body)

if body.count('{') != body.count('}'):
    raise SystemExit('unbalanced braces in the copied CSS - refusing to write')

header = """// Storefront stylesheet, copied verbatim so the phone mock in the builder
// looks exactly like the app. DO NOT hand-edit the copied blocks - re-run
// tools/gen_storefront_scss.py when the storefront changes.
//
// Sources (the storefront repo, components/home/):
//   home.css     whole file
//   extras.css   the "product image gallery" section (.hm-gal-*)
//   cartfx.css   the "floating pill" section (.mc-pill) + its phone @media block
//
// Three mechanical rewrites were applied:
//   @media (max-width: N)  ->  @container mart-phone (max-width: N)
//   vw / vh                ->  cqw / 100%
//   min()/max()/clamp()    ->  #{"..."}, so libsass hands them to the browser
//
// so the app's own breakpoints fire against the frame rather than the window.
// The home editor's canvas is wide (.mart-canvas), so none of them match and
// the desktop rules apply; the product editor's phone is 390px, so they do.
// One stylesheet, both widths - a container query resolves against the
// nearest ancestor carrying the name, and both frames carry `mart-phone`.

"""

override = """

/* ==========================================================================
   Builder-only overrides. Kept separate from the copied blocks above.
   ========================================================================== */
.mart-builder .hm-page {
  /* The mock is static: the app reveals cards and tiles with an
     IntersectionObserver that never fires here. Show them at once. */
  .hm-card, .hm-cat { opacity: 1; transform: none; }
  .hm-banner, .hm-tabs button, .hm-badge, .hm-loc-ic, .hm-off, .hm-add { animation: none; }
  .hm-main { animation: none; }
  /* Sticky header and fixed pills position against the phone frame, not
     the browser window - the frame has layout containment for that. */
  .hm-hdr { position: sticky; top: 0; }
  .hm-tabs-bar { position: static; }
  /* No real scrolling happens inside the mock; let the rails show a hint of
     the next card instead of clipping hard. */
  .hm-rail-track { overflow-x: auto; }
}

/* The desk canvas only. The shop scrolls its banners and tabs sideways; an
   editor has to show every one at once, or the fifth banner is something you
   can change but cannot see. Rails are left scrolling on purpose - a row of
   forty products is a rail, not a wall. */
.mart-builder .mart-canvas .hm-page {
  .hm-banner-track {
    grid-auto-flow: row;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    overflow-x: visible;
    scroll-snap-type: none;
  }
  .hm-banner { height: 100%; }
  .hm-tabs { flex-wrap: wrap; overflow-x: visible; }
}
"""

OUT.write_text(header + body + override, encoding='utf-8', newline='\n')
print('wrote', OUT, '-', len((header + body + override).splitlines()), 'lines')
