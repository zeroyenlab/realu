# -*- coding: utf-8 -*-
"""★★★A/B の1本ぶん。★grow.py の部品を借りて、★小さく回して loss だけ返す。

★★★守ること
  ★① レアルの本物の頭（work/realu.pt）に**触らない**。★読まない・書かない。
  ★② ごはん（棚）は**読むだけ**。
  ★③ 種を固定する。★同じ種なら、A も B も同じ所から始まる。
  ★④ 出すのは `LOSS=数字` の1行だけ。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    import torch
    import grow as G

    seed = int(os.environ.get("REALU_SEED", 0))
    torch.manual_seed(seed)
    G.random.seed(seed)
    torch.set_num_threads(int(os.environ.get("REALU_THREADS", 4)))

    work = os.environ.get("REALU_WORK", os.path.join(HERE, "work"))
    pdir = os.path.join(work, "pantry")
    tokf = os.environ.get("REALU_TOK", os.path.join(work, "tok.json"))
    if not (os.path.isdir(pdir) and os.path.exists(tokf)):
        print("NOPANTRY", flush=True)
        return 1

    pantry = G.Pantry(pdir)
    vocab = G.BpeVocab(tokf)

    # ★★★小さく作る。★本物（幅192・4層）と同じ形を既定にする
    d = int(os.environ.get("REALU_D", 192))
    h = int(os.environ.get("REALU_HEADS", 6))
    n = int(os.environ.get("REALU_LAYERS", 4))
    ctx = int(os.environ.get("REALU_CTX", 256))
    loops = int(os.environ.get("REALU_MAX_LOOPS", 1)) \
        if os.environ.get("REALU_USE_LOOP") == "1" else 1
    model = G.Realu(len(vocab), d=d, h=h, n=n, ctx=ctx, loops=loops).to(G.DEV)

    # ★★物差し。★本物と同じものを使う（★無ければ棚のうしろを借りる）
    valf = os.path.join(work, "val.txt.gz")
    va = None
    if os.path.exists(valf):
        import gzip
        try:
            with gzip.open(valf, "rt", encoding="utf-8", errors="ignore") as f:
                t = f.read()
            ids = []
            for i in range(0, len(t), 4_000_000):
                ids += vocab.encode(t[i:i + 4_000_000])
            if len(ids) > ctx * 8:
                va = torch.tensor(ids, dtype=torch.int32)
        except Exception:
            va = None
    if va is None:
        va = pantry

    steps = int(os.environ.get("REALU_STEPS", 300))
    bs = int(os.environ.get("REALU_BATCH", 16))
    lr = float(os.environ.get("REALU_LR", 3e-4))
    opt = torch.optim.AdamW(model.parameters(), lr=lr,
                            weight_decay=0.01, betas=(0.9, 0.95))

    # ★★三層は grow.py と同じ考え方で（★棚の後ろほど新しい）
    ntot = len(pantry)
    tiers = {"short": (int(ntot * 0.9), ntot), "mid": (int(ntot * 0.5), ntot)}

    model.train()
    for step in range(1, steps + 1):
        warm = min(1.0, step / 50)
        for g in opt.param_groups:
            g["lr"] = lr * warm
        x, y = G.batch(pantry, ctx, bs, tiers)
        _, loss = model(x, y)
        opt.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        opt.step()

    model.eval()
    with torch.no_grad():
        val = torch.stack([model(*G.batch(va, ctx, bs))[1]
                           for _ in range(12)]).mean().item()
    print("LOSS=%.6f" % val, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
