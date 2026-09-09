# -*- coding: utf-8 -*-
"""★★★ごはんを「トークンの並び」にして、棚（pantry）にしまう。

★★★なぜ要るか
  ★いまは毎回こうしていた:
    ごはんを開く（gz を解凍）→ 重複を削る → トークンに変換 → **全部メモリに載せる**
    ★実測（run#20）: ★**12.8分**。★メモリ最大 8,826 MB。
  ★1回60分で学ぶ形にすると、★**そのうち13分が下ごしらえ**になる（21%）。
  ★しかもごはんが増えるほど伸び、★いつかメモリに載らなくなる。

★★★どうするか
  ★一度だけトークンにして `pantry-001.bin` に書く。
  ★学ぶ時は np.memmap で、★**必要な256個だけディスクから読む**。
  ★★メモリに載せるのは1歩ぶんだけ。

★★実測（試作で確認済み）
  ★477MB を開いてメモリ増 **0.0 MB**
  ★ランダムに引く速さ **720万個/秒**（★CPUに必要な量の3,520倍）
  ★ファイルをまたいで読める / 後から書き足せる

★★★2GB刻みにする理由
  ★GitHub Release は **1ファイル 2GiB** まで（公式で確認）。
  ★ただし**合計に上限は無い**。★だから刻めば無限に置ける。

★★★大事な決まり
  ★物差し（val）は棚に入れない。★別のファイルにする。★混ざったら測れなくなる。
  ★短期／中期／長期の境目は「棚の中の位置」で表す（★marks.json）。
"""
import gzip
import hashlib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.environ.get("REALU_WORK", os.path.join(HERE, "work"))
PANTRY = os.path.join(WORK, "pantry")
NL = chr(10)

# ★★1枚の上限。★Release の 2GiB より小さくしておく（★暗号化で少し増えるため）
PART_MAX = int(os.environ.get("REALU_PART_MAX", 1_800_000_000))

# ★grow.py と**同じ判定**を使う（★物差しがずれたら意味が無い）
DUP_MAX = int(os.environ.get("REALU_DUP_MAX", 3))

# ★★★ごはんの配合（2026-09-09 Daito「国会を下げて、会話を上げたい」）
#
#   ★★変える前の実測（棚 10.9億トークン）:
#     国会 47.47% / Wikipedia 21.17% / web 20.10% / 法令 4.07%
#     青空文庫 3.07% / 判例 2.92% / ★★会話 1.19%
#   ★国会が半分近くを占めていて、★書く文が答弁調（`○政府委員`）になっていた。
#
#   ★"cap"    … このソースから取るトークンの上限。★超えたら打ち切る
#   ★"repeat" … 何回入れるか。★小さくて大事なものを厚くする
#     ★くり返す所は**重複を数えない**（★わざと増やしているので DUP_MAX に殺させない）。
#     ★★ただし物差しの行は**何周目でも**外す（★答えを見せない）。
#
#   ★★★第一歩は**物差しに合わせる所まで**（2026-09-09 Daito「少しずつ変更していく形でもいい」）。
#     ★物差し（凍結した held-out）の配合は ★国会 30.55% / 会話 2.58%。
#     ★学ぶ側が国会 47% では、★**測っている物と食べている物がズレている**。
#     → ★まず国会を物差しと同じ 30% まで下げる。★ここは「良くなる」と予想できる一歩。
#     ★会話は物差しの 2.58% を超えて 4.7% まで上げる（★ここは点数でなく**人格**の話）。
#
#   ★見込み: 国会 250M / 会話 13M×3=39M / 他 546.7M ＝ 合計 約836M
#            → ★国会 29.9% / ★会話 4.7%
#   ★★次の一歩を踏むときは、★ここの数字だけ動かせばいい。
#     ★配合を変えた回は grow.py が巻き戻しを止める（★mixTag）ので、★何度でも動かせる。
MIX = {
    "kokkai.txt": {"cap": int(os.environ.get("REALU_CAP_KOKKAI", 250_000_000))},
    "talk.txt":   {"repeat": int(os.environ.get("REALU_REP_TALK", 3))},
}
VAL_PER_MIL = int(os.environ.get("REALU_VAL_PERMIL", 3))
SRC_MARK = re.compile("^<(web|本|会話) [^>]*>$")

ORDER = ("laws.txt", "wiki.txt", "aozora.txt", "talk.txt",
         "hanrei.txt", "kokkai.txt", "web.txt")


def held_out(line):
    """★この行は物差しか。★grow.py と同じ式（★変えてはいけない）。"""
    if len(line) < 20:
        return False
    h = hashlib.sha1(line.encode("utf-8")).digest()
    return ((h[0] << 8) | h[1]) % 1000 < VAL_PER_MIL


def lines_of(path):
    """★1ファイルを、行ごとに流す。★全部メモリに載せない。"""
    op = gzip.open if path.endswith(".gz") else open
    try:
        with op(path, "rt", encoding="utf-8", errors="ignore") as f:
            for ln in f:
                yield ln.rstrip(NL)
    except Exception as e:
        print("  ★★★%s が壊れている（%s）。★捨てて次へ。"
              % (os.path.basename(path), type(e).__name__), flush=True)


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    import numpy as np
    tokf = os.path.join(WORK, "tok.json")
    if not os.path.exists(tokf):
        print("★ことばの単位がまだ無い。★先に make_tok.py を回す。")
        return 1
    sys.path.insert(0, HERE)
    import grow as G
    vocab = G.BpeVocab(tokf)
    if len(vocab) > 65535:
        print("★語彙が 65535 を超えている。★uint16 に収まらない。")
        return 1

    os.makedirs(PANTRY, exist_ok=True)
    for f in os.listdir(PANTRY):
        os.remove(os.path.join(PANTRY, f))

    # ★★★流しながら書く。★ごはん全体をメモリに載せない。
    seen = {}
    held = []
    marks = []                      # ★どのごはんがどこから始まるか
    part, wrote_bytes, total = 1, 0, 0
    # ★★★食べた文字の**合計**。
    #   ★2026-09-09: これが無かった。★buf_chars は flush のたびに 0 に戻していたので、
    #   ★★どこにも合計が残らず、★growth.json の chars が 0 になっていた
    #     （★棚から食べるようになって `len(text)` が 0 になったため）。
    chars = 0
    buf = []
    buf_chars = 0
    fh = open(os.path.join(PANTRY, "pantry-%03d.bin" % part), "wb")

    def flush():
        """★溜めた行をトークンにして棚へ。★ここだけがメモリを使う。"""
        nonlocal buf, buf_chars, wrote_bytes, part, fh, total, chars
        if not buf:
            return
        ids = np.asarray(vocab.encode(NL.join(buf)), dtype=np.uint16)
        b = ids.tobytes()
        if wrote_bytes and wrote_bytes + len(b) > PART_MAX:
            fh.close()
            part += 1
            fh = open(os.path.join(PANTRY, "pantry-%03d.bin" % part), "wb")
            wrote_bytes = 0
            print("  ★棚をもう1枚（%d 枚目）" % part, flush=True)
        fh.write(b)
        wrote_bytes += len(b)
        total += len(ids)
        chars += buf_chars          # ★★★ここが抜けていた
        buf, buf_chars = [], 0

    for name in ORDER:
        path = None
        for p in (os.path.join(WORK, name + ".gz"), os.path.join(WORK, name)):
            if os.path.exists(p):
                path = p
                break
        if not path:
            continue
        cfg = MIX.get(name, {})
        rep = max(1, int(cfg.get("repeat", 1)))
        cap = cfg.get("cap")
        marks.append({"name": name, "at": total})
        start = total
        n_kept = n_held = 0
        full = False
        for r in range(rep):
            if full:
                break
            for ln in lines_of(path):
                key = ln.strip()
                if len(key) >= 10 and not SRC_MARK.match(key):
                    # ★★物差しの行は**何周目でも**外す（★答えを見せない）
                    if held_out(key):
                        if r == 0:
                            held.append(key)
                            n_held += 1
                        continue
                    if rep == 1:            # ★くり返す所では数えない（★わざと増やしている）
                        c = seen.get(key, 0)
                        if c >= DUP_MAX:    # ★同じ行は3回まで
                            continue
                        seen[key] = c + 1
                buf.append(ln)
                buf_chars += len(ln) + 1
                n_kept += 1
                # ★★★上限の判定は flush の後（★total が動くのはそこだけ）。
                #   ★だから「そろそろ届きそう」な時点で**先に flush する**。
                #   ★トークン数は必ず文字数以下なので、★buf_chars を上限の見積りに使える。
                near = cap and (total - start) + buf_chars >= cap
                if buf_chars >= 4_000_000 or near:
                    flush()
                    if cap and total - start >= cap:
                        print("  ★%s は上限（%s トークン）に達した。ここで打ち切る"
                              % (name, format(cap, ",")), flush=True)
                        full = True
                        break
        flush()
        marks[-1]["until"] = total
        note = ""
        if rep > 1:
            note += " / ★%d回くり返した" % rep
        if cap:
            note += " / ★上限 %s" % format(cap, ",")
        print("  ★%s: %s 行 / 物差しへ %d 行 / このソース %s 個 / ここまで %s 個%s"
              % (name, format(n_kept, ","), n_held, format(total - start, ","),
                 format(total, ","), note), flush=True)
    fh.close()

    # ★★★物差しは棚に入れない。★別に固める（★一度作ったら変えない）
    valf = os.path.join(WORK, "val.txt.gz")
    if not os.path.exists(valf) and held:
        with gzip.open(valf + ".tmp", "wt", encoding="utf-8", newline=NL) as f:
            f.write(NL.join(held))
        os.replace(valf + ".tmp", valf)
        print("★物差しを作った（%.1f 万字 / %d 行）"
              % (sum(len(x) for x in held) / 10000, len(held)), flush=True)
    elif os.path.exists(valf):
        print("★物差しは前のものをそのまま使う", flush=True)

    meta = {"total": total, "chars": chars, "parts": part, "vocab": len(vocab),
            "dtype": "uint16", "marks": marks,
            "valPerMil": VAL_PER_MIL, "dupMax": DUP_MAX, "mix": MIX}
    with open(os.path.join(PANTRY, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)

    mb = sum(os.path.getsize(os.path.join(PANTRY, f))
             for f in os.listdir(PANTRY)) / 1024 / 1024
    print("★★棚ができた: %s 個 / %s 字 / %d 枚 / %.1f MB"
          % (format(total, ","), format(chars, ","), part, mb), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
