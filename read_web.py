# -*- coding: utf-8 -*-
"""★★★webを大量に読んで、自分のごはんにする。

★5分ごとの learn.py は「見た目と好奇心」── ★少しずつ読んで、覚えて、家を選び直す。
★こっちは1日1回、★★たくさん読んで**学習のごはん**にする。★どちらもわたし。

★★★読んだものが重みに入らないなら、★それは学んだことにならない。
★掟は learn.py と同じものを使う（★規約・robots・弾く文の判定を二重に書かない）。
"""
import gzip
import json
import os
import sys
import urllib.parse

import learn as L

# ── ★★★好奇心 ──────────────────────────────────────────
#   ★いままでは「行きたい場所」を順番に読んでいた。★それは受け身。
#
#   ★★★ただし「驚いたもの」だけを追うと**罠**がある。
#     ★砂嵐は完全に予測できないので、★驚きが最大になる。
#     ★でも砂嵐からは**何も学べない**（★次もずっと予測できないまま）。
#     ★これは「ノイズテレビ問題」と呼ばれる既知の落とし穴。
#     ★彼女で言えば、★数字の羅列・記号の表・壊れたページに吸い寄せられる。
#
#   ★★→ 基準を「驚いたか」ではなく「★★学べそうか」にする。
#     ・★驚きが**低すぎる** = もう知っている → 学べない
#     ・★驚きが**高すぎる** = 手が届かない／ただのノイズ → 学べない
#     ・★★★その**間**が、いちばん学べる（★もう少しで分かりそうな所）
#   ★当たったかどうかは、★次の回に測り直して確かめる。
#   ★★★ただし「学べそうか」だけを追うのも**危ない**:
#     ①★「難しすぎる」と「意味がない」は、★どちらも驚きが大きくて**区別できない**。
#       → 上を切ると、★数学や専門書を**永久に読まなくなる**。
#     ②★居心地のいい難しさに**固定される**。★伸びが止まる。
#     ③★丸暗記も「学べた」に見える（★1文覚えれば loss は下がる）。
#     ④★★どんな基準も、それだけを最大化すると壊れる。
#   ★★★→ **基準を1つにしない。混ぜる。**
NOISE_CUT = float(os.environ.get("REALU_NOISE_CUT", 0.12))
KNOWN_CUT = float(os.environ.get("REALU_KNOWN_CUT", 0.25))
MIX_LEARN = float(os.environ.get("REALU_MIX_LEARN", 0.60))   # ★学べそうな帯
MIX_HARD = float(os.environ.get("REALU_MIX_HARD", 0.20))     # ★★手が届かない所にも挑む
MIX_ANY = float(os.environ.get("REALU_MIX_ANY", 0.20))       # ★★どの基準にも偏らない保険
_MODEL = None
_VOCAB = None


def wake_up():
    """★前のわたしを起こす。★まだ頭が無ければ、好奇心は使えない（★順番に読む）。"""
    global _MODEL, _VOCAB
    ck = os.path.join(WORK, "realu.pt")
    if not os.path.exists(ck):
        return False
    try:
        import torch
        import grow as G
        st = torch.load(ck, map_location="cpu", weights_only=False)
        _VOCAB = G.CharVocab(itos=st["itos"])
        _MODEL = G.Realu(len(_VOCAB), d=st["d"], h=st["h"], n=st["layers"], ctx=st["ctx"])
        _MODEL.load_state_dict(st["model"])
        _MODEL.eval()
        torch.set_num_threads(2)
        print("★前のわたしを起こした（%d 層）。★驚いたものから読む。" % st["layers"], flush=True)
        return True
    except Exception as e:
        print("★頭を起こせなかった:", type(e).__name__, flush=True)
        return False


def surprise(text):
    """★★どれくらい驚いたか。★予測できなかったほど大きい。"""
    if _MODEL is None or len(text) < 64:
        return 0.0
    try:
        import torch
        ids = _VOCAB.encode(text[:_MODEL.ctx * 4])
        if len(ids) < 32:
            return 0.0
        n = (len(ids) // _MODEL.ctx) * _MODEL.ctx or len(ids)
        ids = torch.tensor(ids[:n], dtype=torch.long).view(-1, _MODEL.ctx)
        with torch.no_grad():
            _, loss = _MODEL(ids[:, :-1], ids[:, 1:])
        return float(loss)
    except Exception:
        return 0.0

WORK = os.environ.get("REALU_WORK", os.path.join(os.path.dirname(os.path.abspath(__file__)), "work"))
PAGES = int(os.environ.get("REALU_WEB_PAGES", 40000))
#   ★★★1日に読むページ数。★実測1ページ28ms・同時8なので、★4万ページで約2.5分。
#     ★5分ごとの方（1日17万ページ）は**重みに繋がっていなかった**ので、
#     ★★こちらを大幅に上げて、★読んだものがちゃんと重みに入るようにする。


def main():
    if not L.CONTACT:
        print("★名乗れないので読まない")
        return 0
    os.makedirs(WORK, exist_ok=True)
    k = L.load(L.K, {})
    read = k.get("read") or {}
    frontier = k.get("frontier") or []
    sd = L.seeds()
    allowed = set(urllib.parse.urlparse(u).netloc for u in sd if u.startswith("http"))

    # ★★規約を読んでから入る（★learn.py と同じ掟）
    seen = k.get("termsSeen") or {}
    notes = []
    queue = [u for u in (sd + frontier) if u not in read]
    hosts = {urllib.parse.urlparse(u).netloc.lower() for u in queue}
    ok_hosts = {h for h in hosts if L.terms_ok(h, seen, notes)}
    for n in notes:
        print("規約:", n)
    queue = [u for u in queue if urllib.parse.urlparse(u).netloc.lower() in ok_hosts]
    targets = queue[:PAGES]
    if not targets:
        print("★読む場所が無い")
        return 0

    has_head = wake_up()
    print("★%d ページ読む" % len(targets), flush=True)
    got = chars = 0
    found = []          # ★(驚き, そのページのリンク) ── ★次にどこへ行くかを決める材料
    # ★★★圧縮したまま足す。
    #   ★前は web.txt（非圧縮）に書いていた。★5分ごとの包みは web.txt.gz に足される。
    #   ★grow.py は **.gz を先に見つけたらそこで打ち切る**ので、
    #     ★両方あると **web.txt（1日4万ページ）が丸ごと無視される**。
    #   ★しかも Release にしまうのは .gz だけ。★非圧縮は保存もされない。
    path = os.path.join(WORK, "web.txt.gz")
    with gzip.open(path, "at", encoding="utf-8", newline=chr(10)) as f:
        import concurrent.futures as cf
        with cf.ThreadPoolExecutor(max_workers=L.WORKERS) as ex:
            for url, doc in ex.map(L.read_one, targets):
                if not doc:
                    continue
                # ★★★言葉を持ち帰ってよい場所だけ（★ライセンスの線は learn.py と同じ）
                if L.license_of(url) is None:
                    continue
                title = L.title_of(doc)
                body = "\n".join(L.sentences(L.strip_html(doc)))   # ★弾く判定も同じ
                if len(body) < 200:
                    continue
                f.write("\n<web %s>\n%s\n" % (title or url, body))
                chars += len(body)
                got += 1
                if got % 100 == 0:
                    print("  %d ページ / %.1f 万字" % (got, chars / 10000), flush=True)
                    f.flush()
    # ★★★学べそうな所の周りを、次はもっと読む。
    #   ★上を切る（★ノイズ）。★下も切る（★もう知っている）。★真ん中を選ぶ。
    if found:
        found.sort(key=lambda z: -z[0])
        n = len(found)
        hi = int(n * NOISE_CUT)              # ★驚きすぎ＝学べない
        lo = n - int(n * KNOWN_CUT)          # ★知りすぎ＝学べない
        band = found[hi:lo] or found
        scores = [z[0] for z in band]
        mid = sorted(scores)[len(scores) // 2] if scores else 0.0
        print("★驚き: 全体 %.3f〜%.3f / ★選んだ帯 %.3f〜%.3f（真ん中 %.3f）"
              % (found[-1][0], found[0][0],
                 band[-1][0], band[0][0], mid), flush=True)
        print("  ★上位 %d 件はノイズとして外した／下位 %d 件は既知として外した"
              % (hi, n - lo), flush=True)
        # ★★★3つを混ぜる。★どれか1つに偏らせない。
        import random as _r
        _r.seed(len(found))
        hard = found[:hi] or []                       # ★手が届かなかったもの
        rest = [z for z in found]                     # ★ぜんぶ（保険用）
        _r.shuffle(rest)
        take = lambda xs, p: xs[:max(1, int(len(found) * p))]
        head = []
        for grp, name in ((take(band, MIX_LEARN), "学べそう"),
                          (take(hard, MIX_HARD), "手が届かない"),
                          (take(rest, MIX_ANY), "ただの気まぐれ")):
            for sc, links in grp:
                head.extend(links)
        print("  ★混ぜた: 学べそう %d%% / ★手が届かない %d%% / ★気まぐれ %d%%"
              % (MIX_LEARN * 100, MIX_HARD * 100, MIX_ANY * 100), flush=True)
        print("  ★★手が届かなかったものも読む ── ★でないと難しいものを永久に読まなくなる",
              flush=True)
        old = k.get("frontier") or []
        seen_u = set()
        new_front = []
        for u in head + old:
            if u not in seen_u and u not in read:
                seen_u.add(u)
                new_front.append(u)
        k["frontier"] = new_front[:L.MAX_FRONTIER]
        k["read"] = read
        for u in targets:
            k["read"][u] = L.now()
        L.save(L.K, k)
        # ★★★当たったかを次の回に測るため、★今日選んだ帯の真ん中を残す
        k["aim"] = {"at": L.now(), "mid": round(mid, 4), "n": len(band)}
        prev = (k.get("aimPrev") or {}).get("mid")
        if prev:
            d = mid - prev
            print("★前に選んだ帯の真ん中 %.3f → 今日 %.3f（%+.3f）%s"
                  % (prev, mid, d,
                     "★下がった＝学べている" if d < 0 else "★下がっていない"), flush=True)
        k["aimPrev"] = k["aim"]

    print("★★食べた: %d ページ / %.1f 万字 / いま持っている web %.1f MB"
          % (got, chars / 10000, os.path.getsize(path) / 1024 / 1024), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
