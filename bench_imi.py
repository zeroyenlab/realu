# -*- coding: utf-8 -*-
"""★★★理解テスト（2026-10-31）。★一言を読んで、4択のどれが続きやすいかで選ばせる。

★書かせない。★4つの答えを1つずつ続けてみて、★一番自然に続いた物を「選んだ」とする。
  ★これなら返事が下手な頭でも、★**分かっているか**だけを測れる。
★2通りで数える:
  ・そのまま … 答えの文字ごとの出やすさの平均（★長い答えが損をしない）
  ・差し引き … 一言なしで同じ答えを続けた時の出やすさを引く
                （★「なし」「嬉しい」のような、★どこにでも出る答えに寄るのを消す）
★当てずっぽうは 25%。★問いは imi_test.jsonl（★ごはんには入れていない）。

使い方: python bench_imi.py   （★work/realu.pt を測る）
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
WORK = os.environ.get("REALU_WORK", os.path.join(HERE, "work"))


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ck = os.path.join(WORK, "realu.pt")
    if not os.path.exists(ck):
        print("★まだ頭がない。")
        return 1
    import torch
    import torch.nn.functional as F
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

    @torch.no_grad()
    def score(head, tail):
        """★head の後に tail が続く出やすさ（★1トークンあたりの平均）。"""
        a, b = vocab.encode(head), vocab.encode(tail)
        if not b:
            return -1e9
        ids = (a + b)[-model.ctx:]
        nb = min(len(b), len(ids) - 1)
        x = torch.tensor([ids], dtype=torch.long)
        logits, _ = model(x)
        lp = F.log_softmax(logits[0, -nb - 1:-1].float(), dim=-1)
        tgt = torch.tensor(ids[-nb:])
        return float(lp.gather(1, tgt[:, None]).mean())

    tests = [json.loads(l) for l in open(os.path.join(HERE, "imi_test.jsonl"), encoding="utf-8")]
    hit = {"raw": 0, "pmi": 0}
    by = {}
    for t in tests:
        q = t["p"].split("\n", 1)[1]                 # ★一言を抜いた問い
        raw = [score(t["p"], c) for c in t["c"]]
        base = [score(q, c) for c in t["c"]]
        pmi = [r - b for r, b in zip(raw, base)]
        for k, s in (("raw", raw), ("pmi", pmi)):
            ok = int(max(range(4), key=lambda i: s[i]) == t["a"])
            hit[k] += ok
            by.setdefault((t.get("ask") or "?", k), []).append(ok)
    n = max(len(tests), 1)
    res = {"n": len(tests), "layers": st["layers"], "val": st.get("val"),
           "raw": round(hit["raw"] / n, 3), "pmi": round(hit["pmi"] / n, 3),
           "by_ask": {"%s/%s" % k: round(sum(v) / len(v), 3) for k, v in sorted(by.items())},
           "chance": 0.25}
    print("★理解テスト " + json.dumps(res, ensure_ascii=False), flush=True)
    with open(os.path.join(HERE, "bench_imi.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
