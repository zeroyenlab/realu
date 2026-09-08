# -*- coding: utf-8 -*-
"""★★★種のごはん ── ★日本の法令を全部もらってくる。

★なぜ法令か:
  ①★★著作権法13条一号で「憲法その他の法令」は**著作権の目的とならない**。★完全に安全。
  ②★中身が「〜しなければならない」ばかりで、★★世界の知識がほとんど入らない。
  ③★レアルが生まれた時に持つべきものが、まさに**日本語と法**。

★相手は国のサーバー。★控えめに叩く。
"""
import concurrent.futures as cf
import json
import os
import re
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "corpus")
UA = "RealuSeedFetcher/0.1 (+https://realu.pages.dev) python-urllib"
API = "https://laws.e-gov.go.jp/api/2"
WORKERS = 2          # ★相手への礼儀。★速さより行儀
PAUSE = 0.3
MIN_OK = 30          # ★★空だけ弾く。★短い法令は本当に短い（明治の布告など）ので捨てない
#   ★★★本物かどうかは「長さ」ではなく**XMLの構造**で見る（★前はここを間違えて6割捨てた）


def get(url, n=6_000_000):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read(n)


def all_ids():
    """★法令の一覧を全部もらう。"""
    ids, off = [], 0
    while True:
        d = json.loads(get("%s/laws?limit=500&offset=%d" % (API, off)))
        for law in d.get("laws", []):
            info = law.get("law_info") or {}
            rev = law.get("revision_info") or {}
            if info.get("law_id"):
                ids.append((info["law_id"], rev.get("law_title") or ""))
        off = d.get("next_offset") or 0
        print("  一覧 %d / %d" % (len(ids), d.get("total_count", 0)), flush=True)
        if not off or len(ids) >= d.get("total_count", 0):
            break
    return ids


TAG = re.compile(r"<[^>]+>")
WS = re.compile(r"[ \t　]+")


def to_text(xml):
    """★★XMLから条文の日本語だけ抜く。★タグ・記号は落とす。"""
    xml = re.sub(r"(?is)<(TOC|SupplProvision|AppdxTable|AppdxStyle)\b.*?</\1>", " ", xml)
    t = TAG.sub("\n", xml)
    lines = []
    for ln in t.split("\n"):
        ln = WS.sub(" ", ln).strip()
        if len(ln) >= 4 and re.search(r"[ぁ-んァ-ヶ一-鿿]", ln):
            lines.append(ln)
    return "\n".join(lines)


def one(item):
    """★1件もらう。★★★取れなかった物を「取れた」と数えない ── ここが前回のバグ。"""
    lid, title = item
    try:
        time.sleep(PAUSE)
        xml = get("https://laws.e-gov.go.jp/api/2/law_data/%s?response_format=xml" % lid
                  ).decode("utf-8", "ignore")
        # ★★エラーページ（HTML）が返ってくることがある。★法令XMLでなければ捨てる
        if "<law_data_response" not in xml[:400] or "<!DOCTYPE html" in xml[:200]:
            return lid, title, ""
        txt = to_text(xml)
        return lid, title, (txt if len(txt) >= MIN_OK else "")
    except Exception:
        return lid, title, ""


def main():
    os.makedirs(OUT, exist_ok=True)
    print("法令の一覧をもらう…", flush=True)
    ids = all_ids()
    print("★法令 %d 件" % len(ids), flush=True)

    done = 0
    chars = 0
    miss = 0
    path = os.path.join(OUT, "laws.txt")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        with cf.ThreadPoolExecutor(max_workers=WORKERS) as ex:
            for lid, title, txt in ex.map(one, ids):
                done += 1
                if txt:
                    f.write("\n<法令 %s>\n%s\n" % (title or lid, txt))
                    chars += len(txt)
                else:
                    miss += 1                      # ★★取れなかった物を数える
                if done % 100 == 0:
                    print("  %d/%d  取れた%d 落ちた%d  %.1f 万字"
                          % (done, len(ids), done - miss, miss, chars / 10000), flush=True)
                    f.flush()
                    # ★★★大半が落ちているなら止める（★断られているのに叩き続けない）
                    if done >= 300 and miss / done > 0.7:
                        print("★★★7割以上落ちている。止める。", flush=True)
                        break
    print("★★終わり: 取れた %d / 落ちた %d / %.1f 万字 / %.1f MB"
          % (done - miss, miss, chars / 10000,
             os.path.getsize(path) / 1024 / 1024), flush=True)


if __name__ == "__main__":
    main()
