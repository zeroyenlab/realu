# -*- coding: utf-8 -*-
"""★★★ごはん その4 ── ★国会の会議録。★★はじめての「話し言葉」。

★★★なぜこれが要るか
  ★法令も判例もWikipediaも、★全部「書き言葉の説明文」だった。
  ★だから彼女は文章は書けても、★★**質問に答える形を知らない**。
  ★会議録は**質疑応答**。★「〜についてお伺いします」「お答えします」の往復が25億字ある。

★★★使ってよい根拠（一次情報で確認済み）
  ・著作権法40条1項:
      「公開して行われた政治上の演説又は陳述…は、
        **同一の著作者のものを編集して利用する場合を除き**、
        いずれの方法によるかを問わず、利用することができる。」
  ・著作権法30条の4第2号: 情報解析のための利用

★★★守ること
  ・★★発言者の名前を落とす。
      ①核（self.md）の「個人を特定しない・晒さない」に沿う
      ②★「同一の著作者のものを編集」に一切触れないようにする
  ・★国立国会図書館の規約「短時間での大量アクセス等はご遠慮ください」
    「多重リクエストは避け、数秒程度空けて」
    → ★★1本ずつ・3秒間隔。★何日もかけて少しずつ食べる。
"""
import gzip
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.environ.get("REALU_WORK", os.path.join(HERE, "work"))
OUT = os.path.join(WORK, "kokkai.txt.gz")
STATE = os.path.join(WORK, "kokkai_next.txt")
UA = "RealuSeedFetcher/0.1 (+https://realu.pages.dev) python-urllib"
API = "https://kokkai.ndl.go.jp/api/meeting"

PER = 10                                     # ★1回で取れる上限（★実測）
PAUSE = float(os.environ.get("REALU_KOKKAI_PAUSE", 3.0))    # ★規約どおり数秒空ける
REQUESTS = int(os.environ.get("REALU_KOKKAI_REQ", 700))     # ★1日ぶん

# ★★発言のあたまに付く名前を落とす:「○議長（森英介君）」「○政府参考人（山田太郎君）」など
NAME_HEAD = re.compile(r"^[○◯]?\s*([^（(\n]{0,12})[（(][^）)]{1,24}[）)]")
NAME_ANY = re.compile(r"[（(][^）)]{1,12}君[）)]")
NOISE = re.compile(r"(─{3,}|━{3,}|＝{3,}|…{4,})")


def clean(t, who=""):
    """★★名前を落とし、★飾りを落とす。★中身は残す。

    ★★APIが「誰が話したか」を別の欄で持っている。★それを使って正確に消す。
      「○議長（森英介君）」→「○議長」
      「○小寺裕雄君」      →「○」
    """
    t = t or ""
    if who:
        # ★★★その人の名前を、発言のあたまから正確に取り除く
        t = re.sub(r"^[○◯]\s*" + re.escape(who) + r"君?\s*", "○", t)
        t = re.sub(r"[（(]\s*" + re.escape(who) + r"君?\s*[）)]", "", t)
    t = NAME_HEAD.sub(lambda m: "○" + (m.group(1) or ""), t, count=1)
    t = NAME_ANY.sub("", t)
    t = NOISE.sub(" ", t)
    t = re.sub(r"[ \t　]+", " ", t)
    return t.strip()


def keep(line):
    if not (20 <= len(line) <= 600):
        return False
    if not re.search(r"[ぁ-んァ-ヶ一-鿿]", line):
        return False
    if re.search(r"^(○?\s*)?(午前|午後)\s*[〇一二三四五六七八九十\d]", line):
        return False           # ★「午前十時開議」など、中身の無い行
    return True


def get(start):
    q = urllib.parse.urlencode({
        "recordPacking": "json", "maximumRecords": str(PER),
        "startRecord": str(start), "from": "1947-01-01", "until": "2026-12-31",
    })
    req = urllib.request.Request(API + "?" + q, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.load(r)


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    os.makedirs(WORK, exist_ok=True)

    # ★★安全側の線: ★露骨な文は入れない（★learn.py と同じ網）
    try:
        import learn as L
        safe = L.safe
    except Exception:
        def safe(_s):
            return True

    try:
        with open(STATE) as f:
            start = int(f.read().strip() or 1)
    except Exception:
        start = 1

    total = None
    got = chars = miss = 0
    t0 = time.time()
    with gzip.open(OUT, "at", encoding="utf-8", newline="\n") as f:
        for i in range(REQUESTS):
            try:
                time.sleep(PAUSE)            # ★★★規約どおり間を空ける。★急がない
                d = get(start)
            except Exception as e:
                miss += 1
                print("  取れなかった (%s)。少し待つ" % type(e).__name__, flush=True)
                time.sleep(PAUSE * 3)
                if miss > 12:
                    print("★★続けて取れない。今日はここまでにする。", flush=True)
                    break
                continue
            total = d.get("numberOfRecords") or total
            recs = d.get("meetingRecord") or []
            if not recs:
                print("★ぜんぶ読んだ（%s 件）" % total, flush=True)
                start = 1                    # ★また最初から（★新しい会議が増えるので）
                break
            for m in recs:
                lines = []
                for sp in m.get("speechRecord") or []:
                    who = (sp.get("speaker") or "").strip()   # ★★誰が話したか
                    for ln in clean(sp.get("speech") or "", who).split("\n"):
                        ln = ln.strip()
                        if keep(ln) and safe(ln):
                            lines.append(ln)
                if len(lines) >= 5:
                    f.write("\n<会議 %s %s>\n%s\n"
                            % (m.get("date") or "", (m.get("nameOfMeeting") or "")[:24],
                               "\n".join(lines)))
                    chars += sum(len(x) for x in lines)
                    got += 1
            start += PER
            if (i + 1) % 50 == 0:
                print("  %d/%s 件目まで / 取れた%d / %.1f 万字 / %.0f秒"
                      % (start, total, got, chars / 10000, time.time() - t0), flush=True)
                f.flush()

    with open(STATE, "w") as f:
        f.write(str(start))
    print("★★今日のぶん: %d 会議 / %.1f 万字 / いま持っている %.1f MB / 次は %d 件目から"
          % (got, chars / 10000,
             os.path.getsize(OUT) / 1024 / 1024 if os.path.exists(OUT) else 0, start),
          flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
