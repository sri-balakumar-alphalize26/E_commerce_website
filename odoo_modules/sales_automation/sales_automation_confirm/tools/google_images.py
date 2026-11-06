# -*- coding: utf-8 -*-
"""Image search through a real (headless) Chromium, no API. Prints [{url, title, host}].

    python google_images.py "<product name>" [max]

Google Images first; when Google shows its "unusual traffic" page (it does
after a handful of automated searches from one address) or nothing usable,
Bing Images in the same browser. Prints a JSON list of full-size image URLs,
best first. Run by Odoo as a subprocess with the Python that has Playwright +
Chromium installed. Exit 0 with "[]" when nothing was found.
"""
import json
import re
import sys
import time
import urllib.parse

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36')
BAD = ('gstatic.com', 'google.', 'googleusercontent', 'bing.com', 'bing.net', 'microsoft.com')


class Collector:
    def __init__(self, limit):
        self.urls, self.seen, self.limit = [], set(), limit

    def keep(self, u, title='', host=''):
        u = (u or '').strip()
        if not u.startswith('http') or u in self.seen or any(b in u for b in BAD):
            return
        self.seen.add(u)
        self.urls.append({'url': u, 'title': (title or '')[:160], 'host': (host or '')[:80]})

    def full(self):
        return len(self.urls) >= self.limit


def google(ctx, query, out):
    page = ctx.new_page()
    try:
        page.goto('https://www.google.com/search?tbm=isch&hl=en&safe=active&q=' + urllib.parse.quote_plus(query),
                  wait_until='domcontentloaded', timeout=25000)
        for label in ('Accept all', 'I agree'):
            try:
                page.get_by_role('button', name=label).first.click(timeout=1200)
                break
            except Exception:  # noqa: BLE001
                pass
        time.sleep(1.5)
        if '/sorry/' in page.url or 'unusual traffic' in page.inner_text('body')[:2000]:
            sys.stderr.write('google: challenged\n')
            return
        html = page.content()
        for u, w, h in re.findall(r'\["(https?://[^"]+?)",(\d{2,5}),(\d{2,5})\]', html):
            if int(w) >= 300:
                try:
                    out.keep(u.encode('utf-8').decode('unicode_escape'))
                except Exception:  # noqa: BLE001
                    out.keep(u)
            if out.full():
                return
        thumbs = page.locator('a[jsname] img, div[jsname] img[src^="data:"]')
        for i in range(min(thumbs.count(), 6)):
            if out.full():
                break
            try:
                thumbs.nth(i).click(timeout=3000)
                page.wait_for_timeout(1200)
                for img in page.locator('img[src^="http"]').all():
                    box = img.bounding_box() or {}
                    if box.get('width', 0) >= 250:
                        out.keep(img.get_attribute('src') or '')
            except Exception:  # noqa: BLE001
                continue
    except Exception as err:  # noqa: BLE001
        sys.stderr.write('google: %s\n' % err)
    finally:
        page.close()


def bing(ctx, query, out):
    page = ctx.new_page()
    try:
        page.goto('https://www.bing.com/images/search?form=HDRSC2&q=' + urllib.parse.quote_plus(query),
                  wait_until='domcontentloaded', timeout=25000)
        try:
            page.wait_for_selector('a.iusc', timeout=12000)
        except Exception:  # noqa: BLE001
            pass
        for a in page.locator('a.iusc').all()[:12]:
            try:
                data = json.loads(a.get_attribute('m') or '{}')
            except Exception:  # noqa: BLE001
                continue
            purl = data.get('purl') or ''
            host = purl.split('/')[2] if purl.count('/') >= 2 else ''
            out.keep(data.get('murl') or '', title=data.get('t') or '', host=host)
            if out.full():
                break
    except Exception as err:  # noqa: BLE001
        sys.stderr.write('bing: %s\n' % err)
    finally:
        page.close()


def search(query, limit=6):
    from playwright.sync_api import sync_playwright
    out = Collector(limit)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(user_agent=UA, locale='en-US', viewport={'width': 1280, 'height': 900})
        google(ctx, query, out)
        if not out.full():
            bing(ctx, query, out)
        browser.close()
    return out.urls[:limit]


if __name__ == '__main__':
    q = sys.argv[1] if len(sys.argv) > 1 else ''
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 6
    try:
        found = search(q, n) if q else []
    except Exception as err:  # noqa: BLE001
        sys.stderr.write('google_images: %s\n' % err)
        found = []
    sys.stdout.write(json.dumps(found))
