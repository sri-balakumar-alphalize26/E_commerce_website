// Builds "369 Mart - Complete Setup & Ordering Guide" (.docx) from the module
// manuals' HTML plus the new chapters in extra.js.
// Usage: node build.js "<documents/odoo documents>" "<out.docx>"
const fs = require('fs');
const path = require('path');
const {
  Document, Packer, Paragraph, TextRun, ImageRun, Table, TableRow, TableCell,
  HeadingLevel, AlignmentType, BorderStyle, ShadingType, WidthType, LevelFormat,
  TableOfContents, Footer, Header, PageNumber, TabStopType, VerticalAlign,
} = require('docx');
const extra = require('./extra');

const ROOT = process.argv[2];
const OUT = process.argv[3];

const C = {
  navy: '1E2A78', orange: 'F08A24', ink: '1F2230', muted: '6B6F80', line: 'E6E8F0',
  alt: 'F2F4FB', tint: 'EEF2FC', tip: '2E6FB0', good: '2E8B57', goodBg: 'E7F6EA',
  warnBg: 'FFF3DA', warnInk: 'C0701A', white: 'FFFFFF', simpleBg: 'FFF8EF',
};
const FONT = 'Calibri';
const PAGE_W = 9638; // A4 width minus 20 mm margins, in DXA
const NOTE = {
  tip: { border: C.tip, bg: C.tint, lbl: C.tip },
  good: { border: C.good, bg: C.goodBg, lbl: C.good },
  imp: { border: C.navy, bg: C.tint, lbl: C.navy },
  warn: { border: C.orange, bg: C.warnBg, lbl: C.warnInk },
  start: { border: C.orange, bg: C.tint, lbl: C.warnInk },
  simple: { border: C.navy, bg: C.simpleBg, lbl: C.orange },
};

// ---------- Chapters, in reading order ----------
const CHAPTERS = [
  { key: 'start', title: 'Start Here', sub: 'What to install, and the order to set things up in', html: extra.start },
  { key: 'flow', title: 'How an Order Works, Start to Finish', sub: 'From the customer\'s tap to the door code', html: extra.flow },
  { mod: 'mart369', title: 'The Foundation' },
  { mod: 'mart369_catalog', title: 'Catalogue & Categories' },
  { mod: 'mart369_product', title: 'Products, Attributes & Variants' },
  { key: 'example', title: 'Your First Product, Step by Step', sub: 'A worked example: one T-shirt in 3 colours and 3 sizes', html: extra.example },
  { mod: 'mart369_home', title: 'The Home Page' },
  { mod: 'mart369_pages', title: 'Footer & Info Pages' },
  { mod: 'mart369_cart', title: 'Delivery, Fees, Slots, Deals & Coupons' },
  { key: 'delivery', title: 'Delivery Setup: Every Step in Order', sub: 'Areas, fees, slots, branches, shops, riders and the counter alarm', html: extra.delivery },
  { mod: 'mart369_address', title: 'Delivery Addresses' },
  { mod: 'mart369_payment', title: 'Payments & the 369 Wallet' },
  { key: 'payment', title: 'Payment Methods Setup: Every Step in Order', sub: 'Card and UPI, cash on delivery, the 369 Wallet, and testing', html: extra.payment },
  { mod: 'mart369_auth', title: 'Customer Sign-In' },
  { mod: 'mart369_roles', title: 'Staff Roles & Riders' },
  { mod: 'mart369_order', title: 'Orders, Returns & Replacements' },
  { mod: 'mart369_store_board', title: 'The Counter (New Orders Board)' },
  { mod: 'mart369_whatsapp_bridge', title: 'WhatsApp: One Shop, Two Doors' },
  { mod: 'mart369_account', title: 'Reviews, Referrals, Rewards & Notifications' },
  { mod: 'mart369_support', title: 'Support Chat & Tickets' },
  { mod: 'mart369_loyalty', title: 'Loyalty Points' },
  { mod: 'pos_loyalty_card', title: 'The Loyalty Card' },
  { mod: 'mart369_parts_demo', title: 'Appendix A: Sample Catalogue', appendix: true },
];

// ---------- A small HTML parser (the manuals are generated and well-formed) ----------
const VOID = new Set(['img', 'br', 'meta', 'hr', 'link']);
function parse(html) {
  const root = { tag: 'root', attrs: {}, children: [] };
  const stack = [root];
  const re = /<!--[\s\S]*?-->|<(\/?)([a-zA-Z0-9]+)((?:\s+[^>]*?)?)\s*(\/?)>|([^<]+)/g;
  let m;
  while ((m = re.exec(html))) {
    if (m[0].startsWith('<!--')) continue;
    if (m[5] !== undefined) { stack[stack.length - 1].children.push({ text: decode(m[5]) }); continue; }
    const tag = m[2].toLowerCase();
    if (m[1]) { // closing
      for (let i = stack.length - 1; i > 0; i--) if (stack[i].tag === tag) { stack.length = i; break; }
      continue;
    }
    const attrs = {};
    m[3].replace(/([a-zA-Z-]+)\s*=\s*"([^"]*)"/g, (_, k, v) => { attrs[k.toLowerCase()] = decode(v); });
    const node = { tag, attrs, children: [] };
    stack[stack.length - 1].children.push(node);
    if (!VOID.has(tag) && !m[4]) stack.push(node);
  }
  return root;
}
function decode(s) {
  return s.replace(/&nbsp;/g, '\u00a0').replace(/&amp;/g, '&').replace(/&gt;/g, '>').replace(/&lt;/g, '<')
    .replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&#(\d+);/g, (_, n) => String.fromCharCode(+n));
}
const cls = (n) => (n.attrs && n.attrs.class ? n.attrs.class.split(/\s+/) : []);
const has = (n, c) => cls(n).includes(c);
const els = (n) => (n.children || []).filter((c) => c.tag);
const textOf = (n) => (n.text !== undefined ? n.text : (n.children || []).map(textOf).join(''));
function find(n, pred) {
  if (pred(n)) return n;
  for (const c of n.children || []) { const r = c.tag && find(c, pred); if (r) return r; }
  return null;
}

// ---------- Inline runs ----------
function runs(node, st = {}, out = []) {
  for (const c of node.children || []) {
    if (c.text !== undefined) {
      const t = c.text.replace(/\s+/g, ' ');
      if (t) out.push({ t, ...st });
      continue;
    }
    const s = { ...st };
    if (c.tag === 'br') { out.push({ br: true }); continue; }
    if (c.tag === 'b' || c.tag === 'strong') s.bold = true;
    if (c.tag === 'i' || c.tag === 'em') s.italics = true;
    if (has(c, 'k') || has(c, 'arr')) { s.bold = true; s.color = has(c, 'arr') ? C.orange : C.navy; }
    if (c._navy) s.color = C.navy;
    runs(c, s, out);
  }
  return out;
}
function toRuns(items, base = {}) {
  // trim leading/trailing spaces of the paragraph
  const list = items.filter((r) => r.br || r.t);
  if (list.length && list[0].t) list[0] = { ...list[0], t: list[0].t.replace(/^\s+/, '') };
  const last = list.length - 1;
  if (last >= 0 && list[last].t) list[last] = { ...list[last], t: list[last].t.replace(/\s+$/, '') };
  return list.filter((r) => r.br || r.t).map((r) => (r.br ? new TextRun({ break: 1 })
    : new TextRun({ text: r.t, bold: r.bold || base.bold, italics: r.italics || base.italics,
      color: r.color || base.color, size: base.size, font: FONT })));
}

// ---------- Images ----------
function pngSize(buf) {
  if (buf.readUInt32BE(0) === 0x89504e47) return { w: buf.readUInt32BE(16), h: buf.readUInt32BE(20) };
  return { w: 1200, h: 800 };
}
const mmToPx = (mm) => (mm * 96) / 25.4;

// ---------- Block conversion ----------
let ctx; // { ch, dir, glossary, figs }
const P = (opts) => new Paragraph({ spacing: { after: 120, line: 276 }, ...opts });

function noteParas(n) {
  const kind = Object.keys(NOTE).find((k) => has(n, k)) || 'tip';
  const st = NOTE[kind];
  const pOpts = {
    shading: { type: ShadingType.CLEAR, fill: st.bg, color: 'auto' },
    border: { left: { style: BorderStyle.SINGLE, size: 30, color: st.border, space: 8 } },
    indent: { left: 200, right: 120 }, spacing: { before: 60, after: 0, line: 264 }, keepLines: true,
  };
  // label + inline text, then any block children as extra shaded paragraphs
  const inline = { children: [] }; const blocks = [];
  for (const c of n.children) {
    if (c.tag && ['p', 'ul', 'div', 'table'].includes(c.tag)) blocks.push(c); else inline.children.push(c);
  }
  const out = [];
  const lbl = inline.children.find((c) => c.tag === 'span' && has(c, 'lbl'));
  const rest = { children: inline.children.filter((c) => c !== lbl) };
  const first = [];
  if (lbl) first.push(new TextRun({ text: textOf(lbl).trim().toUpperCase() + '  ', bold: true, color: st.lbl, size: 18, font: FONT }));
  first.push(...toRuns(runs(rest), { size: 20 }));
  if (first.length) out.push(new Paragraph({ ...pOpts, children: first }));
  for (const b of blocks) {
    if (b.tag === 'ul') for (const li of els(b)) out.push(new Paragraph({ ...pOpts, children: [new TextRun({ text: '•  ', color: st.border, bold: true }), ...toRuns(runs(li), { size: 20 })] }));
    else out.push(new Paragraph({ ...pOpts, children: toRuns(runs(b), { size: 20 }) }));
  }
  // spacing below the box
  out.push(new Paragraph({ spacing: { after: 60 }, children: [] }));
  return out;
}

function cell(children, width, opts = {}) {
  return new TableCell({
    width: { size: width, type: WidthType.DXA },
    margins: { top: 70, bottom: 70, left: 110, right: 110 },
    verticalAlign: opts.vAlign,
    shading: opts.fill ? { type: ShadingType.CLEAR, fill: opts.fill, color: 'auto' } : undefined,
    borders: opts.borders || {
      top: { style: BorderStyle.NONE, size: 0, color: 'auto' },
      left: { style: BorderStyle.NONE, size: 0, color: 'auto' },
      right: { style: BorderStyle.NONE, size: 0, color: 'auto' },
      bottom: { style: BorderStyle.SINGLE, size: 4, color: C.line },
    },
    children,
  });
}

function tableEl(n, glossary) {
  const thead = find(n, (x) => x.tag === 'thead');
  const tbody = find(n, (x) => x.tag === 'tbody') || n;
  const headRow = thead ? els(thead).find((x) => x.tag === 'tr') : null;
  const bodyRows = els(tbody).filter((x) => x.tag === 'tr');
  const ncol = Math.max(...[headRow, ...bodyRows].filter(Boolean).map((r) => els(r).length));
  // widths: from th style width:NN%, rest shared
  const pct = new Array(ncol).fill(null);
  if (headRow) els(headRow).forEach((th, i) => { const m = /width:\s*(\d+)%/.exec(th.attrs.style || ''); if (m) pct[i] = +m[1]; });
  if (has(n, 'gloss') && pct[0] == null) pct[0] = 28;
  const fixed = pct.reduce((a, b) => a + (b || 0), 0);
  const free = pct.filter((x) => x == null).length;
  const widths = pct.map((p) => Math.round(((p != null ? p : (100 - fixed) / Math.max(free, 1)) / 100) * PAGE_W));
  widths[ncol - 1] += PAGE_W - widths.reduce((a, b) => a + b, 0);
  const rows = [];
  if (headRow) {
    rows.push(new TableRow({ tableHeader: true, cantSplit: true, children: els(headRow).map((th, i) => cell(
      [new Paragraph({ spacing: { after: 0 }, children: toRuns(runs(th), { bold: true, color: C.white, size: 19 }) })],
      widths[i], { fill: C.navy })) }));
  }
  bodyRows.forEach((tr, ri) => {
    const tds = els(tr);
    if (glossary && tds.length >= 2) glossary.push({ word: textOf(tds[0]).trim(), node: tds[1], ch: ctx.ch });
    rows.push(new TableRow({ cantSplit: true, children: tds.map((td, i) => cell(
      [new Paragraph({ spacing: { after: 0, line: 252 }, children: toRuns(runs(td), i === 0 ? { bold: true, color: C.navy, size: 19 } : { size: 19 }) })],
      widths[i], { fill: ri % 2 ? C.alt : undefined })) }));
  });
  return [new Table({ width: { size: PAGE_W, type: WidthType.DXA }, columnWidths: widths, rows }), new Paragraph({ spacing: { after: 100 }, children: [] })];
}

function flowEl(n) {
  const cards = els(n).filter((c) => has(c, 'card'));
  const arrowW = 360;
  const cardW = Math.floor((PAGE_W - arrowW * (cards.length - 1)) / cards.length);
  const widths = []; const cells = [];
  const line = { style: BorderStyle.SINGLE, size: 6, color: 'D9DCEA' };
  cards.forEach((card, i) => {
    const b = els(card).find((x) => x.tag === 'b');
    const s = els(card).find((x) => x.tag === 'span');
    widths.push(cardW);
    cells.push(cell([
      new Paragraph({ spacing: { after: 40 }, children: [new TextRun({ text: b ? textOf(b).trim() : '', bold: true, color: C.navy, size: 20, font: FONT })] }),
      new Paragraph({ spacing: { after: 0, line: 240 }, children: [new TextRun({ text: s ? textOf(s).trim() : '', color: C.muted, size: 17, font: FONT })] }),
    ], cardW, { fill: C.tint, borders: { top: { style: BorderStyle.SINGLE, size: 18, color: C.orange }, bottom: line, left: line, right: line } }));
    if (i < cards.length - 1) {
      widths.push(arrowW);
      cells.push(cell([new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 0 }, children: [new TextRun({ text: '→', bold: true, color: C.orange, size: 28 })] })],
        arrowW, { vAlign: VerticalAlign.CENTER, borders: { top: { style: BorderStyle.NONE, size: 0, color: 'auto' }, bottom: { style: BorderStyle.NONE, size: 0, color: 'auto' }, left: { style: BorderStyle.NONE, size: 0, color: 'auto' }, right: { style: BorderStyle.NONE, size: 0, color: 'auto' } } }));
    }
  });
  widths[widths.length - 1] += PAGE_W - widths.reduce((a, b) => a + b, 0);
  return [new Table({ width: { size: PAGE_W, type: WidthType.DXA }, columnWidths: widths, rows: [new TableRow({ cantSplit: true, children: cells })] }), new Paragraph({ spacing: { after: 100 }, children: [] })];
}

function figureEl(n) {
  const img = find(n, (x) => x.tag === 'img');
  const cap = find(n, (x) => x.tag === 'figcaption');
  const out = [];
  if (img) {
    const file = path.join(ctx.dir, img.attrs.src);
    if (!fs.existsSync(file)) { console.warn('MISSING IMAGE', file); ctx.missing.push(file); }
    else {
      const buf = fs.readFileSync(file);
      const { w, h } = pngSize(buf);
      const mh = /max-height:\s*([\d.]+)mm/.exec(img.attrs.style || '');
      const maxH = mmToPx(mh ? +mh[1] : 118) * 0.95;
      const maxW = has(n, 'phone') ? mmToPx(62) : 600;
      const k = Math.min(1, maxW / w, maxH / h);
      out.push(new Paragraph({ alignment: AlignmentType.CENTER, keepNext: true, spacing: { before: 80, after: 60 },
        children: [new ImageRun({ type: 'png', data: buf, transformation: { width: Math.round(w * k), height: Math.round(h * k) },
          altText: { title: img.attrs.alt || 'Screenshot', description: img.attrs.alt || '', name: path.basename(file) } })] }));
      ctx.images++;
    }
  }
  if (cap) out.push(new Paragraph({ spacing: { after: 160 }, children: toRuns(runs(cap), { italics: true, color: C.muted, size: 17 }) }));
  return out;
}

function blocks(node) {
  const out = [];
  for (const n of node.children || []) {
    if (n.text !== undefined) { if (n.text.trim()) out.push(P({ children: toRuns([{ t: n.text }]) })); continue; }
    const t = n.tag;
    if (has(n, 'cover') || has(n, 'topbar') || has(n, 'meta')) continue;
    if (t === 'h2') {
      let s = textOf(n).trim();
      if (s === 'How the manual is arranged') s = 'How this chapter is arranged';
      if (s === "Words you'll see") ctx.inGloss = true; else ctx.inGloss = false;
      out.push(new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun({ text: s })] }));
    } else if (t === 'h3') {
      const num = els(n).find((x) => has(x, 'n'));
      const title = { children: n.children.filter((x) => x !== num) };
      out.push(new Paragraph({ heading: HeadingLevel.HEADING_3, children: [
        ...(num ? [new TextRun({ text: `\u00a0${textOf(num).trim()}\u00a0`, bold: true, color: C.white, shading: { type: ShadingType.CLEAR, fill: C.orange, color: 'auto' } }), new TextRun({ text: '  ' })] : []),
        ...toRuns(runs(title)),
      ] }));
    } else if (has(n, 'part')) {
      out.push(new Paragraph({ alignment: AlignmentType.CENTER, keepNext: true, spacing: { before: 320, after: 140 },
        shading: { type: ShadingType.CLEAR, fill: C.navy, color: 'auto' },
        border: { bottom: { style: BorderStyle.SINGLE, size: 18, color: C.orange, space: 4 } },
        children: [new TextRun({ text: textOf(n).trim().toUpperCase(), bold: true, color: C.white, size: 26, font: FONT })] }));
    } else if (t === 'p' && has(n, 'part-intro')) {
      out.push(P({ children: toRuns(runs(n), { italics: true, color: C.muted }) }));
    } else if (t === 'p') {
      out.push(P({ children: toRuns(runs(n)) }));
    } else if (t === 'ul') {
      const ref = has(n, 'tips') ? 'tips' : 'fbul';
      for (const li of els(n)) {
        const fc = (li.children || []).find((c) => c.tag || (c.text && c.text.trim()));
        if (ref === 'fbul' && fc && fc.tag === 'b') fc._navy = true;
        out.push(new Paragraph({ numbering: { reference: ref, level: 0 }, spacing: { after: 80, line: 264 }, children: toRuns(runs(li)) }));
      }
      out.push(new Paragraph({ spacing: { after: 40 }, children: [] }));
    } else if (t === 'table') {
      out.push(...tableEl(n, ctx.inGloss || has(n, 'gloss') ? ctx.glossary : null));
    } else if (has(n, 'flow')) {
      out.push(...flowEl(n));
    } else if (has(n, 'note')) {
      out.push(...noteParas(n));
    } else if (t === 'figure') {
      out.push(...figureEl(n));
    } else if (['div', 'section', 'body', 'main'].includes(t)) {
      out.push(...blocks(n));
    } else {
      out.push(P({ children: toRuns(runs(n)) }));
    }
  }
  return out;
}

// ---------- Chapter heading band ----------
function chapterHead(num, title, sub, appendix) {
  const band = { type: ShadingType.CLEAR, fill: C.navy, color: 'auto' };
  return [
    new Paragraph({ pageBreakBefore: true, shading: band, spacing: { before: 0, after: 0 }, indent: { left: 0 },
      children: [new TextRun({ text: appendix ? `  ${title.split(':')[0].toUpperCase()}` : `  CHAPTER ${num}`, bold: true, color: C.orange, size: 20, font: FONT })] }),
    new Paragraph({ heading: HeadingLevel.HEADING_1, shading: band, spacing: { before: 0, after: 0 },
      children: [new TextRun({ text: appendix ? title : `${num}.  ${title}`, color: C.white })] }),
    new Paragraph({ shading: band, spacing: { before: 0, after: 0 },
      border: { bottom: { style: BorderStyle.SINGLE, size: 24, color: C.orange, space: 6 } },
      children: [new TextRun({ text: `  ${sub || ''}`, color: 'FFD9A8', size: 22, italics: true, font: FONT })] }),
    new Paragraph({ spacing: { after: 160 }, children: [] }),
  ];
}

// ---------- Cross-references between manuals -> chapters ----------
function fixRefs(html, chNum) {
  const byName = {};
  CHAPTERS.forEach((c, i) => { if (c.mod) byName[c.mod] = i + 1; });
  const names = [
    ['369 Mart Orders', 'mart369_order'], ['Orders', 'mart369_order'], ['369 Mart Roles', 'mart369_roles'], ['Roles', 'mart369_roles'],
    ['369 Mart Sign In', 'mart369_auth'], ['369 Mart Account', 'mart369_account'], ['369 Mart Catalog', 'mart369_catalog'],
    ['369 Mart Payments &amp; Wallet', 'mart369_payment'], ['Loyalty Card', 'pos_loyalty_card'], ['369 Mart Loyalty Points', 'mart369_loyalty'],
  ];
  for (const [name, mod] of names) {
    const re = new RegExp(`(the )?(<b>)?${name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}(</b>)?( user)? manual`, 'g');
    html = html.replace(re, `Chapter ${byName[mod]}`);
  }
  return html
    .replace(/each module's own manual/g, "each part's own chapter").replace(/each module's manual/g, "each part's chapter")
    .replace(/this manual/g, 'this chapter').replace(/This manual/g, 'This chapter')
    .replace(/\bFigure (\d+)\b/g, `Figure ${chNum}.$1`);
}

// ---------- Build ----------
const body = [];
const glossary = [];
let images = 0; const missing = [];
const report = [];

CHAPTERS.forEach((c, i) => {
  const num = i + 1;
  let html; let dir = ROOT; let sub = c.sub;
  if (c.mod) {
    dir = path.join(ROOT, c.mod);
    const file = fs.readdirSync(dir).find((f) => f.endsWith('_User_Manual.html'));
    const raw = fs.readFileSync(path.join(dir, file), 'utf8');
    // One manual has no <body> tag: start after </head> then.
    const from = raw.indexOf('<body>') >= 0 ? raw.indexOf('<body>') + 6 : raw.indexOf('</head>') + 7;
    html = raw.slice(from, raw.lastIndexOf('</body>'));
    const subM = /<div class="sub">([\s\S]*?)<\/div>/.exec(html);
    sub = subM ? decode(subM[1].replace(/<[^>]+>/g, '')).trim() : '';
    html = fixRefs(html, num);
    const h2 = (html.match(/<h2/g) || []).length; const h3 = (html.match(/<h3/g) || []).length;
    report.push({ num, mod: c.mod, h2, h3 });
  } else {
    html = c.html.replace(/\bFigure (\d+)\b/g, `Figure ${num}.$1`);
  }
  ctx = { ch: num, dir, glossary, images: 0, missing, inGloss: false };
  body.push(...chapterHead(num, c.title, sub, c.appendix));
  if (c.mod && extra.simple[c.mod]) {
    const sn = parse(extra.simple[c.mod]);
    const ps = els(sn).filter((x) => x.tag === 'p');
    body.push(...noteParas({ tag: 'div', attrs: { class: 'note simple' }, children: [
      { tag: 'span', attrs: { class: 'lbl' }, children: [{ text: 'In simple words' }] }, ...ps] }));
    body.push(...blocks({ children: els(sn).filter((x) => x.tag !== 'p') }));
  }
  body.push(...blocks(parse(html)));
  images += ctx.images;
});

// ---------- Appendix B: combined glossary ----------
const seen = new Map();
for (const g of glossary) { const k = g.word.toLowerCase(); if (g.word && !seen.has(k)) seen.set(k, g); }
const gl = [...seen.values()].sort((a, b) => a.word.localeCompare(b.word));
body.push(...chapterHead(0, 'Appendix B: Words You\'ll See', 'Every term from every chapter, A to Z', true));
const gw = [2500, PAGE_W - 2500 - 1100, 1100];
body.push(new Table({ width: { size: PAGE_W, type: WidthType.DXA }, columnWidths: gw, rows: [
  new TableRow({ tableHeader: true, children: ['Word', 'What it means', 'Chapter'].map((h, i) => cell([new Paragraph({ spacing: { after: 0 }, children: [new TextRun({ text: h, bold: true, color: C.white, size: 19, font: FONT })] })], gw[i], { fill: C.navy })) }),
  ...gl.map((g, ri) => new TableRow({ cantSplit: true, children: [
    cell([new Paragraph({ spacing: { after: 0 }, children: [new TextRun({ text: g.word, bold: true, color: C.navy, size: 19, font: FONT })] })], gw[0], { fill: ri % 2 ? C.alt : undefined }),
    cell([new Paragraph({ spacing: { after: 0, line: 252 }, children: toRuns(runs(g.node), { size: 19 }) })], gw[1], { fill: ri % 2 ? C.alt : undefined }),
    cell([new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 0 }, children: [new TextRun({ text: String(g.ch), color: C.orange, bold: true, size: 19, font: FONT })] })], gw[2], { fill: ri % 2 ? C.alt : undefined }),
  ] })),
] }));

// ---------- Cover + contents ----------
const band = { type: ShadingType.CLEAR, fill: C.navy, color: 'auto' };
const cover = [
  new Paragraph({ spacing: { before: 1800, after: 0 }, shading: band, children: [] }),
  new Paragraph({ alignment: AlignmentType.CENTER, shading: band, spacing: { after: 0 }, children: [new TextRun({ text: '369 MART', bold: true, color: C.orange, size: 36, font: FONT, characterSpacing: 60 })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, shading: band, spacing: { before: 200, after: 0 }, children: [new TextRun({ text: 'Complete Setup & Ordering Guide', bold: true, color: C.white, size: 60, font: FONT })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, shading: band, spacing: { before: 240, after: 0 }, children: [new TextRun({ text: 'Products · Categories · Attributes & Variants · Delivery · Payments · Orders', color: 'FFD9A8', size: 24, font: FONT })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, shading: band, spacing: { before: 120, after: 0 }, children: [new TextRun({ text: 'Every step, in plain words', italics: true, color: 'D5D9EE', size: 24, font: FONT })] }),
  new Paragraph({ shading: band, spacing: { before: 900, after: 0 }, border: { bottom: { style: BorderStyle.SINGLE, size: 36, color: C.orange, space: 0 } }, children: [] }),
  new Paragraph({ spacing: { before: 600, after: 120 }, alignment: AlignmentType.CENTER, children: [new TextRun({ text: 'For store owners, managers, staff and office teams', bold: true, color: C.navy, size: 24, font: FONT })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: 'User Guide  |  369ai  |  28 October 2026', color: C.muted, size: 20, font: FONT })] }),
  new Paragraph({ pageBreakBefore: true, spacing: { after: 200 }, border: { bottom: { style: BorderStyle.SINGLE, size: 12, color: C.orange, space: 4 } },
    children: [new TextRun({ text: 'Contents', bold: true, color: C.navy, size: 36, font: FONT })] }),
  new TableOfContents('Contents', { hyperlink: true, headingStyleRange: '1-1' }),
];

const doc = new Document({
  creator: '369ai', title: '369 Mart - Complete Setup & Ordering Guide',
  description: 'How to set up products, categories, attributes, variants, delivery, payments and orders.',
  styles: {
    default: { document: { run: { font: FONT, size: 21, color: C.ink } } },
    paragraphStyles: [
      { id: 'Heading1', name: 'Heading 1', basedOn: 'Normal', next: 'Normal', quickFormat: true,
        run: { font: FONT, size: 44, bold: true, color: C.white }, paragraph: { outlineLevel: 0, keepNext: true, indent: { left: 140 } } },
      { id: 'Heading2', name: 'Heading 2', basedOn: 'Normal', next: 'Normal', quickFormat: true,
        run: { font: FONT, size: 30, bold: true, color: C.navy },
        paragraph: { outlineLevel: 1, keepNext: true, spacing: { before: 320, after: 140 }, border: { bottom: { style: BorderStyle.SINGLE, size: 12, color: C.orange, space: 3 } } } },
      { id: 'Heading3', name: 'Heading 3', basedOn: 'Normal', next: 'Normal', quickFormat: true,
        run: { font: FONT, size: 25, bold: true, color: C.navy }, paragraph: { outlineLevel: 2, keepNext: true, spacing: { before: 260, after: 100 } } },
    ],
  },
  numbering: { config: [
    { reference: 'fbul', levels: [{ level: 0, format: LevelFormat.BULLET, text: '■', alignment: AlignmentType.LEFT,
      style: { run: { color: C.orange, size: 14 }, paragraph: { indent: { left: 400, hanging: 260 } } } }] },
    { reference: 'tips', levels: [{ level: 0, format: LevelFormat.BULLET, text: '✔', alignment: AlignmentType.LEFT,
      style: { run: { color: C.good, bold: true }, paragraph: { indent: { left: 400, hanging: 300 } } } }] },
  ] },
  sections: [{
    properties: { titlePage: true, page: { size: { width: 11906, height: 16838 }, margin: { top: 1247, bottom: 1134, left: 1134, right: 1134 } } },
    headers: { first: new Header({ children: [new Paragraph({ children: [] })] }), default: new Header({ children: [new Paragraph({ border: { bottom: { style: BorderStyle.SINGLE, size: 8, color: C.orange, space: 4 } },
      tabStops: [{ type: TabStopType.RIGHT, position: PAGE_W }],
      children: [new TextRun({ text: '369 MART', bold: true, color: C.navy, size: 16, font: FONT }), new TextRun({ text: '\tComplete Setup & Ordering Guide', color: C.muted, size: 16, font: FONT })] })] }) },
    footers: { first: new Footer({ children: [new Paragraph({ children: [] })] }), default: new Footer({ children: [new Paragraph({ border: { top: { style: BorderStyle.SINGLE, size: 6, color: C.line, space: 4 } },
      tabStops: [{ type: TabStopType.RIGHT, position: PAGE_W }],
      children: [new TextRun({ text: '369ai · 369 Mart Guide', color: C.muted, size: 16, font: FONT }), new TextRun({ children: ['\tPage ', PageNumber.CURRENT], color: C.navy, bold: true, size: 16, font: FONT })] })] }) },
    children: [...cover, ...body],
  }],
});

Packer.toBuffer(doc).then((buf) => {
  fs.writeFileSync(OUT, buf);
  console.log('WROTE', OUT, (buf.length / 1048576).toFixed(1) + ' MB', 'images', images, 'glossary', gl.length, 'missing', missing.length);
  for (const r of report) console.log('ch', r.num, r.mod, 'h2', r.h2, 'h3', r.h3);
});
