"""Turn each manual PDF into page PNGs for review. Usage: py pages.py "<odoo documents dir>" <outdir> [module ...]"""
import sys, pathlib, fitz

root, out, *only = sys.argv[1:]
out = pathlib.Path(out)
for pdf in sorted(pathlib.Path(root).glob('*/*_User_Manual.pdf')):
    mod = pdf.parent.name
    if only and mod not in only:
        continue
    doc = fitz.open(pdf)
    (out / mod).mkdir(parents=True, exist_ok=True)
    for i, page in enumerate(doc, 1):
        page.get_pixmap(dpi=60).save(out / mod / f'p{i:02d}.png')
    print(f'{mod}: {doc.page_count} pages')
