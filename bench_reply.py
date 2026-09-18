# -*- coding: utf-8 -*-
"""★★★返事の選び方を、★**手元で何度でも試せる形**にして書き出す。

★★なぜ要るか（★2026-09-18）
  ★選び方のつまみ（★ありふれ具合をどれだけ引くか・下限・長さ）を、
    ★★**2例だけ見て回していた**。★片方を直すと片方が壊れる、を繰り返した。
  ★★★つまみは5つある。★2例で5つ決めるのは**当てずっぽう**と変わらない。
  → ★★**一度の走行で何十例ぶんの候補表を書き出す**。★あとは手元で何度でも試せる。
    ★頭を動かすのは1回だけ。★つまみを回すのに GitHub を待たなくてよくなる。

★出すもの: `bench_reply.json`
  [{"said": 相手の言葉,
    "cand": [{"t": 返事, "ctx": 文脈での出やすさ, "any": ありふれ具合,
              "loop": 繰り返し, "copy": まね}, ...]}, ...]

使い方: python bench_reply.py            （★下の SAYS を使う）
        python bench_reply.py "言葉1" "言葉2" …
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
WORK = os.environ.get("REALU_WORK", os.path.join(HERE, "work"))
OUT = os.path.join(HERE, "bench_reply.json")

# ★★話しかけられそうな言葉を、★短いもの・長いもの・質問・つぶやき で散らす
SAYS = [
    "おなかすいた", "今日は暑かったね", "こんばんは", "ねむい",
    "今日は何してたの？", "元気？", "ありがとう", "つかれた",
    "どこに住んでるの？", "好きな食べ物は？", "雨がふってきた",
    "明日は休みなんだ", "この前の話だけどさ", "ちょっと聞いてよ",
    "なんか面白いことない？", "お仕事どう？", "さむくなってきたね",
    "おはよう", "また今度ね", "それでどうなったの？",
]


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    says = [a for a in sys.argv[1:] if a.strip()] or SAYS
    ck = os.path.join(WORK, "realu.pt")
    if not os.path.exists(ck):
        print("★まだ頭がない。")
        return 1

    import torch
    import reply as R
    import grow as G
    torch.set_num_threads(int(os.environ.get("REALU_THREADS", 4)))

    st = torch.load(ck, map_location="cpu", weights_only=False)
    tokf = os.environ.get("REALU_TOK", os.path.join(WORK, "tok.json"))
    vocab = (G.BpeVocab(tokf) if (st.get("kind") == "bpe" and os.path.exists(tokf))
             else G.CharVocab(itos=st["itos"]))
    model = G.Realu(len(vocab), d=st["d"], h=st["h"], n=st["layers"],
                    ctx=st["ctx"], loops=st.get("loops", 1))
    model.load_state_dict(st["model"])
    try:
        G.attach_kana(model, vocab, quiet=True)
    except Exception:
        pass
    model.eval()
    print("★頭: %d 層 / %.2f M / loss %.4f"
          % (st["layers"], sum(p.numel() for p in model.parameters()) / 1e6,
             st.get("val") or 0), flush=True)
    try:
        import learn as L
        safe = L.safe
    except Exception:
        def safe(_s):
            return True

    NEUTRAL = "%s「" % R.ME
    out = []
    for i, said in enumerate(says):
        prompt = R.build_prompt([said])
        seen, cand = set(), []
        for _ in range(R.TRIES):
            try:
                t = R.cut(G.no_src(R.gen(model, vocab, prompt, R.MAXTOK, R.TEMP, R.TOPP)))
            except Exception:
                continue
            if not t or t in seen or not safe(t):
                continue
            seen.add(t)
            cand.append(t)
        rows = []
        for t in cand:
            rows.append({"t": t,
                         "ctx": round(R.score(model, vocab, prompt, t + "」"), 4),
                         "any": round(R.score(model, vocab, NEUTRAL, t + "」"), 4),
                         "loop": round(max(R.loops(t), R.echo(t)), 2),
                         "copy": round(R.copied(t, said), 2)})
        out.append({"said": said, "cand": rows})
        print("  %2d/%d 「%s」 %d 本" % (i + 1, len(says), said, len(rows)), flush=True)

    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        json.dump({"layers": st["layers"], "val": st.get("val"),
                   "params": sum(p.numel() for p in model.parameters()),
                   "cases": out}, f, ensure_ascii=False, indent=1)
        f.write("\n")
    n = sum(len(c["cand"]) for c in out)
    print("★★★書き出した: %d 例 / %d 本の候補 → %s" % (len(out), n, os.path.basename(OUT)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
