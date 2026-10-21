#!/usr/bin/env python3
"""Книга (PDF/EPUB) → текстовые файлы по страницам/главам для конспектирования.

  python tools/book_text.py references/books/itten.pdf --out references/notes/_raw/itten
Затем Claude читает файлы по порядку и пишет references/notes/<имя>.md (см. references/books/README.md).
PDF — нужен pdftotext (poppler); EPUB — стандартная библиотека. Сканы без текстового слоя дают пустые страницы (нужен OCR).
"""
import argparse
import os
import re
import subprocess
import sys
import zipfile
from html.parser import HTMLParser


class Strip(HTMLParser):
    def __init__(self):
        super().__init__(); self.out = []; self.skip = False
    def handle_starttag(self, t, a):
        if t in ("script", "style"): self.skip = True
        if t in ("p", "div", "br", "h1", "h2", "h3", "li"): self.out.append("\n")
    def handle_endtag(self, t):
        if t in ("script", "style"): self.skip = False
    def handle_data(self, d):
        if not self.skip: self.out.append(d)


def pdf(path, out):
    n = int(re.search(r"Pages:\s+(\d+)", subprocess.run(["pdfinfo", path], capture_output=True, text=True).stdout).group(1))
    empty = 0
    for i in range(1, n + 1):
        t = subprocess.run(["pdftotext", "-layout", "-f", str(i), "-l", str(i), path, "-"], capture_output=True, text=True).stdout
        if len(t.strip()) < 20: empty += 1
        open(os.path.join(out, f"p{i:04d}.txt"), "w", encoding="utf-8").write(t)
    return n, empty


def epub(path, out):
    z = zipfile.ZipFile(path)
    names = sorted(n for n in z.namelist() if n.lower().endswith((".xhtml", ".html", ".htm")))
    for i, n in enumerate(names, 1):
        p = Strip(); p.feed(z.read(n).decode("utf-8", "replace"))
        open(os.path.join(out, f"c{i:04d}.txt"), "w", encoding="utf-8").write(re.sub(r"\n{3,}", "\n\n", "".join(p.out)))
    return len(names), 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("book"); ap.add_argument("--out", required=True)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    n, empty = (epub if a.book.lower().endswith(".epub") else pdf)(a.book, a.out)
    print(f"{n} частей → {a.out}" + (f"; пустых {empty} — возможно скан без текстового слоя (нужен OCR)" if empty > n * 0.3 else ""))


if __name__ == "__main__":
    main()
