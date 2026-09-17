# -*- coding: utf-8 -*-
"""★★★いまある国会のごはんを、★取り直さずに往復の形へ組み直す。

★★なぜ取り直さなくていいか（★2026-09-16 に気づいた）
  ★`fetch_kokkai.clean()` は、★発言のあたまの名前を **`○`** に置き換えている。
  ★★つまり `kokkai.txt.gz` の中で、★**`○` で始まる行＝誰かが話し始めた所**。
  ★名前は消えているが、★★**切れ目だけは残っている**。
  → ★だから 685MB をその場で読み直せば、★往復の形に戻せる。

★★★買い足しは止めてある（★冷蔵庫に1GB以上あり、まだ0.016周しか使っていないため）。
  ★だから「これから取る分だけ新形式」では**一生効かない**。★ここが要る。

★★分かっていること・いないこと（★正直に）
  ★分かる: ★**どこで話者が変わったか**（★`○` の位置）
  ★★分からない: ★**誰が話したか**。★同じ人が続けて話したのかどうかも分からない。
  → ★★★**2人の往復として組む**（AA / AB を交互）。
    ★狙いは「1番ぶんの次は**相手**の番」を覚えさせること。★1対1で話すための形。
    ★実際の会議では議長が挟まったり同じ人が続くこともあるので、★そこは近似。
    ★★名前を出さないのは元のまま（★著作権法40条／個人を晒さない）。

使い方: python to_kaiwa.py     （★kaiwa.txt.gz が既にあれば何もしない）
"""
import gzip
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.environ.get("REALU_WORK", os.path.join(HERE, "work"))
SRC = os.path.join(WORK, "kokkai.txt.gz")
OUT = os.path.join(WORK, "kaiwa.txt.gz")
TURN_MAX = int(os.environ.get("REALU_TURN_MAX", 400))
HEAD = re.compile(r"^<会議 ")


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


def pieces(body):
    """★長い答弁は句点で切る（★同じ人のまま）。"""
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
    if not os.path.exists(SRC):
        print("★もとの国会のごはんが無い。★何もしない")
        return 0
    SIG = os.path.join(WORK, "kaiwa_recipe.txt")
    need, old = stale(OUT, SIG, os.path.abspath(__file__))
    if not need:
        print("★往復のごはんはもうある（%.0f MB）。★組み直し方も変わっていない。★何もしない"
              % (os.path.getsize(OUT) / 1e6))
        return 0
    if os.path.exists(OUT):
        print("★★組み直し方が変わった（%s → %s）。★組み直す"
              % (old or "なし", recipe(os.path.abspath(__file__))), flush=True)

    tmp = OUT + ".tmp"
    n_meet = n_turn = n_line = n_cont = 0
    chars = 0
    sample = []
    try:
        with gzip.open(SRC, "rt", encoding="utf-8", errors="ignore") as f, \
                gzip.open(tmp, "wt", encoding="utf-8", newline="\n") as g:
            cur, side = "", 0

            def flush():
                nonlocal cur, n_turn, chars
                if not cur.strip():
                    cur = ""
                    return
                tag = "AA" if side == 0 else "AB"
                for p in pieces(cur.strip()):
                    g.write(tag + "「" + p + "」\n")
                    n_turn += 1
                    chars += len(p)
                    if len(sample) < 6:
                        sample.append(tag + "「" + p[:54] + "…」")
                cur = ""

            def take(ln):
                nonlocal side, cur, n_meet, n_cont
                if HEAD.match(ln):
                    flush()
                    # ★★会議ごとに振り直す。★次の `○` で反転して AA から始まるよう 1 を入れる
                    side = 1
                    g.write("\n" + ln + "\n")
                    n_meet += 1
                    return
                s = ln.strip()
                if not s:
                    return
                if s[0] in "○◯":            # ★★誰かが話し始めた
                    flush()
                    side = 1 - side          # ★次の番は相手
                    cur = s[1:].strip()
                else:                        # ★同じ人の続き
                    cur += (" " if cur else "") + s
                    n_cont += 1

            # ★★★途中で読めなくなっても、★そこまでを残す（★grow.py と同じ構え）。
            #   ★`kokkai.txt.gz` は**継ぎ足しで作った多重メンバーの gz**。
            #   ★★どこか1つのメンバーが途中で切れていると `zlib.error` で止まる。
            #   ★実測（走行#224）: ★ここで落ちて**1行も作れていなかった**。
            #   → ★読めた所までで組み直す。★全部捨てるより、★8割でも入るほうが良い。
            it = iter(f)
            while True:
                try:
                    ln = next(it)
                except StopIteration:
                    break
                except Exception as ex:
                    print("★途中で読めなくなった（%s）。★%s 行目までを残す"
                          % (type(ex).__name__, format(n_line, ",")), flush=True)
                    break
                n_line += 1
                take(ln.rstrip("\n"))
            flush()
        os.replace(tmp, OUT)
        with open(SIG, "w", encoding="utf-8") as f:
            f.write(recipe(os.path.abspath(__file__)))
    except Exception as e:
        print("★組み直せなかった（%s）" % type(e).__name__, flush=True)
        try:
            os.remove(tmp)
        except Exception:
            pass
        return 1

    print("★★★往復の形に組み直した")
    print("  もと      : %.0f MB / %s 行" % (os.path.getsize(SRC) / 1e6, format(n_line, ",")))
    print("  できたもの: %.0f MB / %s 番 / %.1f 億字"
          % (os.path.getsize(OUT) / 1e6, format(n_turn, ","), chars / 1e8))
    print("  1番ぶんの長さ: 平均 %.0f 字（★上限の目安 %d）"
          % (chars / max(1, n_turn), TURN_MAX))
    print("  続きの行  : %s（★`○` が無い行＝同じ人の続きとして繋いだ）"
          % format(n_cont, ","))
    print("― できたものの頭 ―")
    for s in sample:
        print("   ", s)
    return 0


if __name__ == "__main__":
    sys.exit(main())
