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


def write(model, vocab, start, n, temp, guard, top_p=0.9):
    """★★★1つの発話だけを書く（★2026-11-04）。

    ★前は `model.write()` で**改行を越えて**書き、★no_src が改行を空白にしていた。
      ★材料は「1行に1発話（`AA「…」`）」なので、★頭は改行の次に**次の人の札**を書く。
      ★★それがそのまま出て「…」 AA「…」になっていた（★60回のうち57回に札）。
    → ★改行が出たらそこで止める。★裾は切る（★reply.py と同じ top-p）。★字が壊れる単位は選ばない。
    """
    import torch
    import torch.nn.functional as F
    from reply import _top_p
    ok, nxt_t = guard if guard else (None, None)
    ids = (vocab.encode(start) or [0])[-model.ctx:]
    idx = torch.tensor([ids], dtype=torch.long)
    use_cache = model.loops == 1
    caches = [[] for _ in model.blocks] if use_cache else None
    new, s, ends = [], 0, []   # ★ends: 字の切れ目にいた所（★半端を落とす時に戻る先）
    with torch.no_grad():
        if use_cache:
            logits, _ = model(idx, caches=caches, pos=0)
            pos = idx.shape[1]
        else:
            logits, _ = model(idx)
        for _ in range(n):
            lg = logits[0, -1] / temp
            if ok is not None:
                lg = lg.masked_fill(~ok[s], float("-inf"))
            p = _top_p(F.softmax(lg, dim=-1).unsqueeze(0), top_p)
            nxt = int(torch.multinomial(p, 1).item())
            new.append(nxt)
            if ok is not None:
                s = nxt_t[s][nxt]
            if s == 0:
                ends.append(len(new))
                if "\n" in vocab.decode(new[-2:]):
                    break
            t = torch.tensor([[nxt]], dtype=torch.long)
            if use_cache and pos < model.ctx:
                logits, _ = model(t, caches=caches, pos=pos)
                pos += 1
            else:
                full = torch.tensor([(ids + new)[-model.ctx:]], dtype=torch.long)
                if use_cache:
                    caches = [[] for _ in model.blocks]
                    logits, _ = model(full, caches=caches, pos=0)
                    pos = full.shape[1]
                else:
                    logits, _ = model(full)
    if ok is not None:
        new = new[:ends[-1]] if ends else []   # ★最後に字の半端が残ったら落とす
    return start + vocab.decode(new).split("\n")[0]


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
    tokf = os.environ.get("REALU_TOK", os.path.join(WORK, "tok.json"))
    if st.get("kind") == "bpe" and os.path.exists(tokf):
        vocab = G.BpeVocab(tokf)
    else:
        vocab = G.CharVocab(itos=st["itos"])
    model = G.Realu(len(vocab), d=st["d"], h=st["h"], n=st["layers"],
                    ctx=st["ctx"], loops=st.get("loops", 1))
    model.load_state_dict(st["model"])
    # ★★★五十音の座標を入れ直す（★2026-09-16）。
    #   ★`kana_feat` は .pt に入らない（persistent=False）ので、★ここで作り直さないと
    #     ★★**学習した時と違う埋め込み表**で書くことになる。
    #   ★実測: これが無かった間、★サイトに出る文章だけが
    #     ★「せいせいせいせい」「ははははは」と壊れていた。
    #     ★同じ頭で grow.py が書いたものは普通に読めていたので、★頭のせいに見えなかった。
    try:
        G.attach_kana(model, vocab)
    except Exception as e:
        print("★五十音の座標を入れられなかった（%s）" % type(e).__name__, flush=True)
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

    # ★★★字の表（★2026-11-04）。★ByteLevel でない頭（文字単位）では使わない
    guard = None
    if getattr(vocab, "kind", "") == "bpe":
        try:
            import utf8_guard as U
            tb = U.token_bytes(vocab.t)
            if tb:
                guard = U.table(tb)
        except Exception as e:
            print("★字の表を作れなかった（%s）" % type(e).__name__, flush=True)

    wrote = []
    for pr in STARTS:
        try:
            t = G.no_src(write(model, vocab, pr, 120, 0.8, guard))
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
