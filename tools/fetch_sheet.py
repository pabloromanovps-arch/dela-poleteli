#!/usr/bin/env python3
"""Таблица → CSV UTF-8 для шаблонов: Google Sheets (ссылка), .xlsx или .csv в другой кодировке.

  python tools/fetch_sheet.py "https://docs.google.com/spreadsheets/d/<ID>/edit#gid=0" data/players.csv
  python tools/fetch_sheet.py players.xlsx data/players.csv --sheet "Игроки"
"""
import argparse
import csv
import io
import re
import urllib.request


def from_google(url):
    m = re.search(r"/d/([\w-]+)", url)
    gid = re.search(r"gid=(\d+)", url)
    export = f"https://docs.google.com/spreadsheets/d/{m.group(1)}/export?format=csv&gid={gid.group(1) if gid else 0}"
    with urllib.request.urlopen(export, timeout=60) as r:
        return list(csv.reader(io.StringIO(r.read().decode("utf-8"))))


def from_xlsx(path, sheet):
    import openpyxl
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    ws = wb[sheet] if sheet else wb.active
    return [["" if v is None else str(v) for v in row] for row in ws.iter_rows(values_only=True)]


def from_csv(path):
    raw = open(path, "rb").read()
    for enc in ("utf-8-sig", "cp1251"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    dialect = csv.Sniffer().sniff(text.splitlines()[0], delimiters=",;\t")
    return list(csv.reader(io.StringIO(text), dialect))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("src")
    p.add_argument("out")
    p.add_argument("--sheet")
    a = p.parse_args()
    if a.src.startswith("http"):
        rows = from_google(a.src)
    elif a.src.lower().endswith((".xlsx", ".xlsm")):
        rows = from_xlsx(a.src, a.sheet)
    else:
        rows = from_csv(a.src)
    rows = [r for r in rows if any(c.strip() for c in r)]
    header = [h.strip() for h in rows[0]]
    if "id" not in header:
        print("ВНИМАНИЕ: нет колонки id — она нужна для имён файлов (скилл data-driven-templates)")
    with open(a.out, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows[1:])
    print(f"{len(rows) - 1} строк, колонки: {', '.join(header)} → {a.out}")


if __name__ == "__main__":
    main()
