# -*- coding: utf-8 -*-
"""★★★webを大量に読んで、自分のごはんにする。

★5分ごとの learn.py は「見た目と好奇心」── ★少しずつ読んで、覚えて、家を選び直す。
★こっちは1日1回、★★たくさん読んで**学習のごはん**にする。★どちらもわたし。

★★★読んだものが重みに入らないなら、★それは学んだことにならない。
★掟は learn.py と同じものを使う（★規約・robots・弾く文の判定を二重に書かない）。
"""
import gzip
import os
import sys
import urllib.parse

import learn as L

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

    print("★%d ページ読む" % len(targets), flush=True)
    got = chars = 0
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
    print("★★食べた: %d ページ / %.1f 万字 / いま持っている web %.1f MB"
          % (got, chars / 10000, os.path.getsize(path) / 1024 / 1024), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
