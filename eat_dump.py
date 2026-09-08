# -*- coding: utf-8 -*-
"""★★★まとめて食べる ── ★Wikipedia日本語版のダンプを、正面から受け取る。

★★★なぜスクレイピングでなくダンプか
  ★Wikimedia は「大量に欲しいならスクレイピングでなく**ダンプを使え**」と言っている。
  ★140万ページを叩きに行くのは、★★相手にとって迷惑な行為。
  ★ダンプなら1回で全部もらえて、★相手のサーバーにも優しい。★速くて礼儀正しい。

★ライセンス: ★本文は CC BY-SA 4.0。
  ★学習に使う根拠は著作権法30条の4第2号（情報解析）。
  ★★引用として表示するときは出典とライセンスを必ず出す（★家の側で実装済み）。

★1回動かせば終わり。★2回目からは「もう持っている」と言って何もしない。
"""
import bz2
import html as H
import os
import re
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.environ.get("REALU_WORK", os.path.join(HERE, "work"))
URL = "https://dumps.wikimedia.org/jawiki/latest/jawiki-latest-pages-articles.xml.bz2"
UA = "RealuSeedFetcher/0.1 (+https://realu.pages.dev) python-urllib"
OUT = "wiki.txt"
MAX_CHARS = int(os.environ.get("REALU_DUMP_CHARS", 1_200_000_000))

NL = chr(10)

# ★★ウィキ記法を落とす。★順番が大事:
#   ①★先に &lt; を < に戻す（★戻さないとタグの網にかからない）
#   ②★★テンプレート {{...}} は入れ子。★内側から繰り返し剥がす
#   ③★表・インフォボックスの行（| や ! で始まる）は文ではないので落とす
INNER_T = re.compile(r"\{\{[^{}]*\}\}")
INNER_TB = re.compile(r"(?s)\{\|[^{|]*?\|\}")
BAR_LINE = re.compile(r"^\s*[|!]")
DROP = [
    (re.compile(r"(?s)<ref[^>]*/>"), " "),
    (re.compile(r"(?s)<ref[^>]*>.*?</ref>"), " "),
    (re.compile(r"(?s)<!--.*?-->"), " "),
    (re.compile(r"<[^>]+>"), " "),
    (re.compile(r"\[\[(?:ファイル|File|画像|Image|Category|カテゴリ)[^\]]*\]\]"), " "),
    (re.compile(r"\[\[[^\]|]*\|([^\]]*)\]\]"), r"\g<1>"),
    (re.compile(r"\[\[([^\]]*)\]\]"), r"\g<1>"),
    (re.compile(r"\[https?://\S+\s([^\]]*)\]"), r"\g<1>"),
    (re.compile(r"https?://\S+"), " "),
    (re.compile(r"(?m)^[*#:;]+"), " "),
    (re.compile(r"'{2,}"), ""),
    (re.compile(r"={2,}[^=]*={2,}"), NL),
]


def clean(t):
    t = H.unescape(H.unescape(t))
    for _ in range(8):
        t2 = INNER_TB.sub(" ", INNER_T.sub(" ", t))
        if t2 == t:
            break
        t = t2
    t = re.sub(r"(?s)\{\{.*?\}\}", " ", t)
    t = re.sub(r"(?s)\{\|.*?\|\}", " ", t)
    for pat, rep in DROP:
        t = pat.sub(rep, t)
    t = NL.join(l for l in t.split(NL) if not BAR_LINE.match(l))
    t = re.sub(r"[ \t　]+", " ", t)
    return re.sub(NL + "{2,}", NL, t).strip()


def keep(line):
    """★覚える価値のある文だけ。★learn.py と同じ考え方。"""
    if not (25 <= len(line) <= 400):
        return False
    if not re.search(r"[ぁ-んァ-ヶ一-鿿]", line):
        return False
    if len(re.findall(r"[ 　]", line)) > len(line) / 12:
        return False           # ★一覧の断片
    if line.count("=") > 2 or line.startswith("|"):
        return False           # ★テンプレートの引数の残り
    return True


def main():
    os.makedirs(WORK, exist_ok=True)
    out = os.path.join(WORK, OUT)
    if os.path.exists(out) and os.path.getsize(out) > 100_000_000:
        print("★もう持っている（%.1f MB）" % (os.path.getsize(out) / 1024 / 1024))
        return 0

    # ★★安全側の線: ★露骨な文は入れない（★learn.py と同じ網を使う）
    try:
        import learn as L
        safe = L.safe
    except Exception:
        def safe(_s):
            return True

    print("★ダンプをもらいに行く（4.4GB）…", flush=True)
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    t0 = time.time()
    chars = pages = 0
    buf = []
    title = ""
    intext = False

    with urllib.request.urlopen(req, timeout=180) as r:
        dec = bz2.BZ2Decompressor()
        tail = ""
        with open(out, "w", encoding="utf-8", newline=NL) as f:
            while chars < MAX_CHARS:
                chunk = r.read(4 << 20)
                if not chunk:
                    break
                try:
                    raw = dec.decompress(chunk)
                except EOFError:
                    break
                if not raw:
                    continue
                s = tail + raw.decode("utf-8", "ignore")
                if len(s) > 4096:
                    tail, s = s[-4096:], s[:-4096]
                else:
                    tail = ""

                for line in s.split(NL):
                    if "<title>" in line:
                        m = re.search(r"<title>(.*?)</title>", line)
                        title = m.group(1) if m else ""
                        # ★★記事以外（利用者・ノート・カテゴリ等）は入れない
                        intext = ":" not in title
                    elif "<text" in line:
                        buf = [line.split(">", 1)[-1]]
                    elif "</text>" in line:
                        buf.append(line.split("</text>")[0])
                        if intext and buf:
                            body = clean(NL.join(buf))
                            good = [l.strip() for l in body.split(NL)
                                    if keep(l.strip()) and safe(l.strip())]
                            if len(good) >= 3:
                                f.write(NL + "<記事 " + title + ">" + NL
                                        + NL.join(good) + NL)
                                chars += sum(len(g) for g in good)
                                pages += 1
                                if pages % 20000 == 0:
                                    print("  %d 記事 / %.2f 億字 / %.0f秒"
                                          % (pages, chars / 1e8, time.time() - t0),
                                          flush=True)
                                    f.flush()
                        buf = []
                    elif buf:
                        buf.append(line)

    print("★★食べた: %d 記事 / %.2f 億字 / %.1f MB / %.0f秒"
          % (pages, chars / 1e8, os.path.getsize(out) / 1024 / 1024, time.time() - t0),
          flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
