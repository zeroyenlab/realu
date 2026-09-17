# -*- coding: utf-8 -*-
"""★★★ごはん ── ★ゲームのシナリオ（★くだけた話し言葉）。

★★なぜ要るか（★2026-09-17）
  ★棚の中身を数えたら、★**会話は 3〜4% しかない**。★残りは書き言葉か国会答弁。
  ★だから「〜でございます」調に寄る。★1対1で話すための材料が足りない。
  ★★★ゲームのシナリオは ①現代語 ②往復の形 ③**感情の幅がある** ──
    ★いま棚に無いものが全部そろっている。

★★★出どころ: 日本語オープンコンテンツデータセット プロジェクト
  https://gitlab.com/open_contents_datasets/Rosebleu
  ★解散した Rosebleu ブランドの10タイトル。★**権利者（青猫様）の許諾つき**で、
  ★「営利・非営利の制限は不要」として **APACHE LICENSE 2.0** で公開されている。
  ★★だから ①再配布してよい ②改変（往復の形に組み直す）してよい ③商用も可。
  ★他の候補（日本語日常対話・名大会話コーパス）は **改変禁止(ND)** なので、
    ★★往復に組み直すこと自体ができず、★レアルには使えなかった。

★★★成人向けの扱い（★ここを外すと公開している文章に混ざる）
  ★元は成人向け美少女ゲーム。★配布元は「該当ファイルには名前に `h` が付く」と言う。
  ★★だが実測では **695本中17本にしか印が無い**。★印だけには頼らない。
  → ★★★三重にする:
     ①名前に `h` の付くファイルを丸ごと外す
     ②`learn.safe()`（★レアルが元から持っている網）を**1発話ずつ**かける
     ③★さらに広い網（★情感的な描写）を**取り込む時に**かける
  ★実測（★印の無い8本・961発話）: ★①の網 0.00% / ③の網 0.31%。
  ★★落とした数は必ず印字する。★黙って通さない。
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
sys.path.insert(0, HERE)
WORK = os.environ.get("REALU_WORK", os.path.join(HERE, "work"))
OUT = os.path.join(WORK, "game.txt.gz")
TURN_MAX = int(os.environ.get("REALU_TURN_MAX", 400))
UA = "RealuSeedFetcher/0.1 (+https://realu.pages.dev) python-urllib"
PROJ = "open_contents_datasets%2FRosebleu"
API = "https://gitlab.com/api/v4/projects/" + PROJ
PAUSE = float(os.environ.get("REALU_GAME_PAUSE", 0.4))

# ★★★③の網。★`learn.safe()`（臨床的な語）では拾えない、★情感的な描写を落とす
# ★★★③の網。★`learn.safe()`（臨床的な語）では拾えない描写を落とす。
#   ★★★2026-09-17 に**締めすぎを直した**（Daito「そんなのは下ネタには入らない」）。
#   ★前は `胸を` `舌を` `息が荒` `快感` `抱きしめ` `下着` `脱が` `裸` まで入れていた。
#     ★実測で落ちていたのは ── 「★胸を撫で下ろす」（＝安心する）
#       「★舌を出して恥ずかしがる」（＝てへぺろ）「★息が荒い。全身が汗でびっしょり」（＝運動後）
#       「★マッサージ……快感！」──★★**6語のうち4語が意味の取り違え**だった。
#   ★★落としすぎると、★**ほしかった自然な言い回しごと消える**。
#     ★そもそも `裸足` `裸眼` `靴を脱ぐ` `コートを脱ぐ` も巻き込む。
#   → ★★**それ単体で性的な語だけ**にする。★普通の文脈で出る語は入れない。
#   ★臨床的な語（性交・性器・全裸 等）は `learn.safe()` が別に見ている。★ここは重ねない。
WIDE = re.compile("(喘[ぎぐ]|あえぎ声|愛撫|挿入|絶頂|咥え|淫|情事|欲情|艶めか|"
                  "唇を奪|肌を重|エッチ|素っ裸|前戯|絶倫)")


def recipe(path):
    """★★★この係の「作り方」の指紋。★網を変えたら変わる。

    ★★★2026-09-17 に踏みかけた: ★網をゆるめたのに、★`もうあるから何もしない` で
      ★**締めすぎの網で取ったものが固定される**所だった。
      ★★前に「1回だけの印」で同じ型を踏んでいる（★2026-09-15）。
    ★`make_pantry.py` の作り直し判定（★`sha1sum make_pantry.py`）と同じ作法にする。
    """
    import hashlib
    try:
        return hashlib.sha1(io_open(path).encode("utf-8")).hexdigest()[:12]
    except Exception:
        return ""


def io_open(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def stale(out, sigfile, me):
    """★作り直すべきか。★出来上がりが無い／作り方が変わった、なら作り直す。"""
    if not os.path.exists(out):
        return True, ""
    try:
        with open(sigfile, encoding="utf-8") as f:
            old = f.read().strip()
    except Exception:
        old = ""
    now = recipe(me)
    return (old != now), old


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    return urllib.request.urlopen(req, timeout=60).read()


def listing():
    """★★jsonl の一覧。★名前に `h` が付くものは**ここで外す**。"""
    out, skipped = [], 0
    for p in range(1, 20):
        try:
            d = json.loads(get(API + "/repository/tree?recursive=true"
                               "&per_page=100&page=" + str(p)).decode("utf-8"))
        except Exception as e:
            print("★一覧が取れなかった（%s）" % type(e).__name__, flush=True)
            break
        if not d:
            break
        for x in d:
            if x.get("type") != "blob" or not x["path"].endswith(".jsonl"):
                continue
            if re.search(r"h_converted\.jsonl$", x["path"]):
                skipped += 1          # ★★成人向けの印
                continue
            out.append(x["path"])
        time.sleep(PAUSE)
    return out, skipped


def pieces(body):
    """★長い語りは句点で切る（★同じ人のまま）。"""
    out, cur = [], ""
    for s in re.split(r"(?<=。)", body):
        if cur and len(cur) + len(s) > TURN_MAX:
            out.append(cur.strip())
            cur = ""
        cur += s
    if cur.strip():
        out.append(cur.strip())
    return out


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    os.makedirs(WORK, exist_ok=True)
    SIG = os.path.join(WORK, "game_recipe.txt")
    need, old = stale(OUT, SIG, os.path.abspath(__file__))
    if not need:
        print("★ゲームのごはんはもうある（%.1f MB）。★作り方も変わっていない。★何もしない"
              % (os.path.getsize(OUT) / 1e6))
        return 0
    if os.path.exists(OUT):
        print("★★作り方が変わった（%s → %s）。★取り直す"
              % (old or "なし", recipe(os.path.abspath(__file__))), flush=True)
        os.remove(OUT)
    try:
        import learn as L
        safe = L.safe
    except Exception:
        def safe(_s):
            return True

    paths, skipped_h = listing()
    if not paths:
        print("★取れなかった。★何もしない")
        return 0
    print("★%d 本を読む（★成人向けの印がついた %d 本は外した）"
          % (len(paths), skipped_h), flush=True)

    tmp = OUT + ".tmp"
    n_turn = n_drop_ng = n_drop_wide = n_file = 0
    chars = 0
    sample = []
    with gzip.open(tmp, "wt", encoding="utf-8", newline="\n") as g:
        for i, path in enumerate(paths):
            u = (API + "/repository/files/" + urllib.parse.quote(path, safe="")
                 + "/raw?ref=main")
            try:
                txt = get(u).decode("utf-8", "replace")
            except Exception:
                continue
            title = path.split("/")[0]
            tag_of, order, lines = {}, 0, []
            for ln in txt.splitlines():
                if not ln.strip():
                    continue
                try:
                    o = json.loads(ln)
                except Exception:
                    continue
                s = (o.get("utterance") or "").strip()
                who = (o.get("speaker") or "").strip()
                if len(s) < 4:
                    continue
                if not safe(s):
                    n_drop_ng += 1
                    continue
                if WIDE.search(s):
                    n_drop_wide += 1
                    continue
                # ★★人の名前は出さない。★記号は**作品ごとに振り直す**（★国会と同じ作法）
                if who not in tag_of:
                    tag_of[who] = chr(65 + order // 26) + chr(65 + order % 26)
                    order += 1
                for p in pieces(s):
                    lines.append(tag_of[who] + "「" + p + "」")
                    chars += len(p)
            if len(lines) >= 4:
                g.write("\n<物語 %s>\n%s\n" % (title, "\n".join(lines)))
                n_turn += len(lines)
                n_file += 1
                if len(sample) < 6:
                    sample += lines[:2]
            if (i + 1) % 100 == 0:
                print("  %d/%d 本 / %s 番 / %.1f 万字"
                      % (i + 1, len(paths), format(n_turn, ","), chars / 10000), flush=True)
            time.sleep(PAUSE)
    os.replace(tmp, OUT)
    with open(SIG, "w", encoding="utf-8") as f:
        f.write(recipe(os.path.abspath(__file__)))

    print("★★★ゲームのごはんができた")
    print("  %s 番 / %.1f 万字 / %.1f MB（★%d 本の物語から）"
          % (format(n_turn, ","), chars / 10000, os.path.getsize(OUT) / 1e6, n_file))
    print("  ★落としたもの: 成人向けの印 %d 本（ファイルごと） / "
          "レアルの網 %s 発話 / 広い網 %s 発話"
          % (skipped_h, format(n_drop_ng, ","), format(n_drop_wide, ",")))
    print("― できたものの頭 ―")
    for s in sample[:6]:
        print("   ", s[:72])
    return 0


if __name__ == "__main__":
    sys.exit(main())
