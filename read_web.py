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
#   ★★「知らないことを減らす」なら、★★★**自分が予測できなかったもの**を優先すべき。
#   ★読む前には分からないので、★読んだ結果で次の行き先が変わる形にする。
#   ★驚いたページの周りを、次はもっと読む。
#   （★見ているだけでは学べない／自分で動いて結果を見て初めて学べる、の実装）
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
PAGES = int(os.environ.get("REALU_WEB_PAGES", 600))     # ★1日に読むページ数


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
    path = os.path.join(WORK, "web.txt")
    with open(path, "a", encoding="utf-8", newline="\n") as f:
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
    # ★★★驚いたページの周りを、次はもっと読む。★行きたい場所の順番を並べ替える。
    #   ★★★注意: ★前に入れるということは、★**後ろが押し出される**ということ。
    #     ★押し出されるのは「昔から行きたかった場所」。★だから上限を大きく取ってある。
    #     ★それでも溢れたら、★黙って捨てずに数える（★何か所諦めたかを残す）。
    if found:
        found.sort(key=lambda z: -z[0])
        head = []
        for sc, links in found[:len(found) // 3 + 1]:
            head.extend(links)
        old = k.get("frontier") or []
        seen_u = set()
        new_front = []
        for u in head + old:
            if u not in seen_u and u not in read:
                seen_u.add(u)
                new_front.append(u)
        if len(new_front) > L.MAX_FRONTIER:
            k["gaveUp"] = int(k.get("gaveUp") or 0) + (len(new_front) - L.MAX_FRONTIER)
            print("★行きたい場所が多すぎる。%d か所を諦めた"
                  % (len(new_front) - L.MAX_FRONTIER), flush=True)
        k["frontier"] = new_front[:L.MAX_FRONTIER]
        k["read"] = read
        for u in targets:
            k["read"][u] = L.now()
        L.save(L.K, k)
        top = found[0][0]
        low = found[-1][0]
        print("★驚き: いちばん %.3f / いちばん低い %.3f → ★驚いた方の周りを先に読む"
              % (top, low), flush=True)

    print("★★食べた: %d ページ / %.1f 万字 / いま持っている web %.1f MB"
          % (got, chars / 10000, os.path.getsize(path) / 1024 / 1024), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
