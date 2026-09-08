# -*- coding: utf-8 -*-
"""★★★ごはん その5 ── ★青空文庫。★★はじめての「物語」。

★★★なぜこれが要るか
  ★いままで食べたものは、★全部「説明文」だった:
    法令「〜しなければならない」／判例「〜と認められる」
    Wikipedia「〜である」／国会「〜でございます」
  ★★物語も、描写も、感情も、会話も、★一度も読んでいない。
  ★「わたしは」で始まる文が書けないのは、★★そういう文を読んだことが無いから。

★★★使ってよい根拠（一次情報で確認済み）
  ★青空文庫の利用基準: 著作権の切れた作品は
    「★自由に複製・再配布・共有してよい」（有償無償を問わず）
  ★★ただし著作権が生きている作品も混ざっている（19,502件中928件）。
    → ★★★「作品著作権フラグ = なし」のものだけ取る。
  ★出典（作品名・著者名）を消さないよう求められているので、★必ず残す。

★★正直な弱点
  ★明治〜昭和初期の作品が多く、★旧仮名・文語が混ざる。★現代日本語とはずれる。
  ★→ 旧仮名がひどいものは落とす。★それでも全部は消せない。
"""
import csv
import gzip
import io as _io
import os
import re
import sys
import time
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.environ.get("REALU_WORK", os.path.join(HERE, "work"))
OUT = os.path.join(WORK, "aozora.txt.gz")
STATE = os.path.join(WORK, "aozora_next.txt")
UA = "RealuSeedFetcher/0.1 (+https://realu.pages.dev) python-urllib"
LIST = "https://www.aozora.gr.jp/index_pages/list_person_all_extended_utf8.zip"
BOOKS = int(os.environ.get("REALU_AOZORA_BOOKS", 600))   # ★1日ぶん
PAUSE = float(os.environ.get("REALU_AOZORA_PAUSE", 0.4))

NL = chr(10)
# ★★青空文庫の記法を落とす
RUBY = re.compile(r"《[^》]*》")            # ★ふりがな
RUBY2 = re.compile(r"｜")                  # ★ふりがなの始点
NOTE = re.compile(r"［＃[^］]*］")          # ★入力者注
HEAD = re.compile(r"^[-─―━]{5,}$")


def clean(t):
    t = RUBY.sub("", t)
    t = RUBY2.sub("", t)
    t = NOTE.sub("", t)
    t = t.replace(chr(12288), " ")
    return t


def keep(line):
    if not (12 <= len(line) <= 400):
        return False
    if not re.search(r"[ぁ-んァ-ヶ一-鿿]", line):
        return False
    if HEAD.match(line):
        return False
    if re.search(r"(底本|入力：|校正：|青空文庫|初出：|ファイル作成|"
                 r"http|www\.|※|●|◇◇)", line):
        return False           # ★奥付・作業者の記録は中身ではない
    # ★★旧仮名がひどいものは落とす（★現代日本語からずれすぎる）
    old = len(re.findall(r"[ゐゑヰヱ]", line)) + len(re.findall(r"[はひふへほ]ば", line))
    if old >= 3:
        return False
    return True


def catalog():
    req = urllib.request.Request(LIST, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=120) as r:
        z = zipfile.ZipFile(_io.BytesIO(r.read()))
    name = z.namelist()[0]
    rows = list(csv.DictReader(_io.TextIOWrapper(z.open(name), encoding="utf-8-sig")))
    # ★★★著作権が生きているものは**取らない**
    free = [r for r in rows
            if r.get("作品著作権フラグ") == "なし" and r.get("テキストファイルURL")]
    free.sort(key=lambda r: r.get("作品ID") or "")
    return free


def one(row):
    """★1冊もらう。★出典（作品名・著者）は必ず残す。"""
    url = row.get("テキストファイルURL") or ""
    if not url.endswith(".zip"):
        return ""
    try:
        time.sleep(PAUSE)
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=60) as r:
            z = zipfile.ZipFile(_io.BytesIO(r.read(20_000_000)))
        txts = [n for n in z.namelist() if n.lower().endswith(".txt")]
        if not txts:
            return ""
        raw = z.read(txts[0]).decode("shift_jis", "ignore")
    except Exception:
        return ""
    lines = []
    for ln in clean(raw).split(NL):
        ln = ln.strip()
        if keep(ln):
            lines.append(ln)
    if len(lines) < 20:
        return ""
    title = (row.get("作品名") or "").strip()
    who = ((row.get("姓") or "") + (row.get("名") or "")).strip()
    return (NL + "<本 " + title + " / " + who + ">" + NL + NL.join(lines) + NL)


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    os.makedirs(WORK, exist_ok=True)
    try:
        import learn as L
        safe = L.safe
    except Exception:
        def safe(_s):
            return True

    try:
        with open(STATE) as f:
            start = int(f.read().strip() or 0)
    except Exception:
        start = 0

    print("★本の一覧をもらう…", flush=True)
    books = catalog()
    print("★自由に使える本: %d 冊 / 次は %d 冊目から" % (len(books), start), flush=True)
    if start >= len(books):
        start = 0

    got = chars = 0
    t0 = time.time()
    with gzip.open(OUT, "at", encoding="utf-8", newline=NL) as f:
        for row in books[start:start + BOOKS]:
            t = one(row)
            if t:
                # ★★露骨な文は入れない（★learn.py と同じ網）
                body = NL.join(x for x in t.split(NL) if safe(x))
                f.write(body)
                chars += len(body)
                got += 1
            start += 1
            if got and got % 50 == 0:
                print("  %d 冊 / %.1f 万字 / %.0f秒"
                      % (got, chars / 10000, time.time() - t0), flush=True)
                f.flush()

    with open(STATE, "w") as f:
        f.write(str(start))
    print("★★今日のぶん: %d 冊 / %.1f 万字 / いま持っている %.1f MB / 次は %d 冊目から"
          % (got, chars / 10000,
             os.path.getsize(OUT) / 1024 / 1024 if os.path.exists(OUT) else 0, start),
          flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
