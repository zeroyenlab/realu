# -*- coding: utf-8 -*-
"""★★★書いてみる ── ★頭で、いま書けるものを書く。

★育つのは1日1回だが、★★**書くのはもっと頻繁でいい**。
★同じ書き出しで書かせて並べれば、★育ちが目で見える。

★★★出す前に必ず検閲する（★learn.py と同じ言葉の網）。
★★書いたものは knowledge/design と同じく、★公開される前提で扱う。
"""
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.environ.get("REALU_WORK", os.path.join(HERE, "work"))
HIST = os.path.join(HERE, "growth.json")
SAID = os.path.join(HERE, "said.json")     # ★書いたものの記録（★これだけ別に持つ）

# ★毎回おなじ書き出し。★変えない（★変えたら比べられない）
STARTS = ["わたしは", "第一条", "この法律において", "きょうは", "人は"]
KEEP = int(os.environ.get("REALU_SAID_KEEP", 60))


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ck = os.path.join(WORK, "realu.pt")
    if not os.path.exists(ck):
        print("★まだ頭がない。書けない。")
        return 0

    import torch
    import grow as G
    torch.set_num_threads(int(os.environ.get("REALU_THREADS", 4)))

    st = torch.load(ck, map_location="cpu", weights_only=False)
    tokf = os.path.join(WORK, "tok.json")
    if st.get("kind") == "bpe" and os.path.exists(tokf):
        vocab = G.BpeVocab(tokf)
    else:
        vocab = G.CharVocab(itos=st["itos"])
    model = G.Realu(len(vocab), d=st["d"], h=st["h"], n=st["layers"],
                    ctx=st["ctx"], loops=st.get("loops", 1))
    model.load_state_dict(st["model"])
    model.eval()
    print("★頭を起こした: %d 層 / %.2f M / loss %.4f"
          % (st["layers"], sum(p.numel() for p in model.parameters()) / 1e6,
             st.get("val") or 0), flush=True)

    # ★★出す前の検閲（★learn.py と同じ網）
    try:
        import learn as L
        safe = L.safe
    except Exception:
        def safe(_s):
            return True

    wrote = []
    for pr in STARTS:
        try:
            t = re.sub(r"\s+", " ", model.write(vocab, pr, 120, temp=0.8)).strip()
            if not safe(t):
                t = "（出せない言葉が混じったので、これは出さない）"
            wrote.append({"start": pr, "text": t[:240]})
            print("【%s】%s" % (pr, t[:110]), flush=True)
        except Exception as e:
            print("  書けなかった:", type(e).__name__, flush=True)

    try:
        with open(SAID, encoding="utf-8") as f:
            said = json.load(f)
    except Exception:
        said = {"list": []}
    said["list"].append({
        "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "val": st.get("val"), "layers": st.get("layers"),
        "params": sum(p.numel() for p in model.parameters()),
        "wrote": wrote,
    })
    said["list"] = said["list"][-KEEP:]
    with open(SAID, "w", encoding="utf-8", newline="\n") as f:
        json.dump(said, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print("★%d 回ぶん残っている" % len(said["list"]), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
