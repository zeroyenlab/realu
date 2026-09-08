# -*- coding: utf-8 -*-
"""★★★種のごはん その2 ── ★裁判所の判決文。

★なぜ判決か:
  ①★★著作権法13条**三号**で「裁判所の判決」は**著作権の目的とならない**。★法令と同じく安全。
  ②★★法令だけだと「〜しなければならない」しか書けない子になる。
    ★判決には「〜した」「〜と認められる」という**普通の文**がある。★文章が書けるようになる。
  ③★体系的な世界知識はほとんど入らない。

★★★個人情報について（★これが一番大事）
  ★判決文には**弁護士名・代表者名**などが載っている。
  ★レアルの核（self.md）は「★個人を特定しない・晒さない」と決めている。
  → ★★**当事者の記載を丸ごと落とす**。★「主文」より前は捨てる。
  → ★★残った中の「代理人」「弁護士」「裁判官」の行も落とす。

★相手は国のサーバー。★控えめに叩く。
"""
import concurrent.futures as cf
import io
import os
import re
import sys
import time
import urllib.request

from pypdf import PdfReader

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "corpus")
UA = "RealuSeedFetcher/0.1 (+https://realu.pages.dev) python-urllib"
BASE = "https://www.courts.go.jp/assets/hanrei/hanrei-pdf-%d.pdf"
WORKERS = 2          # ★相手への礼儀
PAUSE = 0.4
MIN_CHARS = 400      # ★これ未満は中身が無かったとみなす

CJK = r"぀-ヿ㐀-鿿＀-￯"


def clean(t):
    """★★PDFから抜いた字を、読める日本語に戻す。"""
    t = t.replace("　", " ")
    # ★行番号（余白に振ってある 5 10 15 20 25 …）を落とす。
    #   ★★5の倍数だけを狙う ── ★本文中の数字（金額・年月日）を壊さないため
    t = re.sub(r"(?m)^\s*\d{1,3}\s*$", "\n", t)
    LN = r"(?:5|10|15|20|25|30|35|40|45|50|55|60)"
    t = re.sub(r"(?<![0-9０-９])" + LN + r"[ \t]*(?=\n)", "", t)
    t = re.sub(r"(?<![0-9０-９])" + LN + r"[ \t]*$", "", t, flags=re.M)
    # ★★字の間に入ってしまった空白を詰める（原 告 → 原告）
    for _ in range(3):
        t = re.sub(r"(?<=[%s])[ \t]+(?=[%s])" % (CJK, CJK), "", t)
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


# ★★★個人が写り込む行を落とす
PERSON_LINE = re.compile(
    r"(訴訟代理人|復代理人|補佐人|弁護士|弁理士|司法書士|代表者|代表取締役|代表役員|"
    r"裁判長|裁判官|裁判所書記官|書記官|調査官|住所|本籍|氏名)")

# ★★氏名が載る行は**短い**（役職＋名前だけ）。★本文は長い。
#   ★長さで分ければ、★★名前だけ消して中身を残せる。
#   ★「被告人は〜した」のような本文は役職語を含むが長いので残る。
NAME_LINE_MAX = 40


def deidentify(t):
    """★★★当事者の記載を落とす ── ★「主文」より前は丸ごと捨てる。"""
    m = re.search(r"主\s*文", t)
    if m:
        t = t[m.start():]                      # ★当事者・代理人の一覧はここより前にある
    keep = [ln for ln in t.split("\n")
            if not (PERSON_LINE.search(ln) and len(ln.strip()) <= NAME_LINE_MAX)]
    return "\n".join(keep).strip()


# ★★★入れないもの ── ★性的な事件の判決は、事実の記述が生々しい。
#   ★これを覚えると、★★彼女がそれを書いてしまう。★公開の場に出す以上、入口で止める。
#   ★根拠: 刑法175条（わいせつ物頒布等）／児童ポルノ禁止法／各プラットフォームの規約。
#   ★★「読まない」のが一番確実。★出口だけで止めようとしない。
NG_CASE = re.compile(
    r"(強制性交|不同意性交|準強制性交|強制わいせつ|不同意わいせつ|準強制わいせつ|"
    r"公然わいせつ|わいせつ物|わいせつ電磁的記録|児童買春|児童ポルノ|"
    r"売春防止法|淫行|性的姿態|盗撮|性的な部位)")
NG_HITS = 2          # ★1回だけなら引用の可能性。★2回以上なら事件そのもの


def is_ng(t):
    return len(NG_CASE.findall(t)) >= NG_HITS


def one(pid):
    """★1件もらう。★★取れなかった物を取れたと数えない／取れた物を捨てない。"""
    try:
        time.sleep(PAUSE)
        req = urllib.request.Request(BASE % pid, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=60) as r:
            b = r.read(20_000_000)
        if not b.startswith(b"%PDF"):
            return pid, ""
        rd = PdfReader(io.BytesIO(b))
        raw = "\n".join((p.extract_text() or "") for p in rd.pages)
        t = deidentify(clean(raw))
        if is_ng(t):
            return pid, ""            # ★★性的な事件は丸ごと入れない
        return pid, (t if len(t) >= MIN_CHARS else "")
    except Exception:
        return pid, ""


def main(start, stop, step=1, tag=""):
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, "hanrei%s.txt" % tag)
    ids = list(range(start, stop, step))
    done = miss = chars = 0
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        with cf.ThreadPoolExecutor(max_workers=WORKERS) as ex:
            for pid, t in ex.map(one, ids):
                done += 1
                if t:
                    f.write("\n<判決 %d>\n%s\n" % (pid, t))
                    chars += len(t)
                else:
                    miss += 1
                if done % 50 == 0:
                    print("  %d/%d  取れた%d 落ちた%d  %.1f 万字"
                          % (done, len(ids), done - miss, miss, chars / 10000), flush=True)
                    f.flush()
    n = done - miss
    print("★★終わり: 取れた %d / 落ちた %d / %.1f 万字 / 1件あたり %d 字 / %.1f MB"
          % (n, miss, chars / 10000, chars / max(1, n),
             os.path.getsize(path) / 1024 / 1024), flush=True)


if __name__ == "__main__":
    a = sys.argv[1:]
    main(int(a[0]), int(a[1]), int(a[2]) if len(a) > 2 else 1,
         a[3] if len(a) > 3 else "")
