# -*- coding: utf-8 -*-
"""★同じ実効深さで、ループ回数を変えて比べる。★パラメータをどれだけ減らせて、何を失うか。"""
import io, math, sys, time, torch
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import grow as G

txt = io.open("../seed/corpus/laws.txt", encoding="utf-8").read(4_000_000)
V = G.CharVocab(text=txt)
ids = torch.tensor(V.encode(txt), dtype=torch.long)
tr, va = ids[:int(len(ids)*.98)], ids[int(len(ids)*.98):]
CTX, BS, D, H, STEPS = 128, 12, 128, 4, 600
torch.set_num_threads(4)

print("%-16s %8s %8s %10s" % ("構成", "実効層", "パラメータ", "loss"), flush=True)
res = []
for n, lp in [(8, 1), (4, 2), (2, 4), (1, 8)]:
    torch.manual_seed(0)
    m = G.Realu(len(V), d=D, h=H, n=n, ctx=CTX, loops=lp)
    opt = torch.optim.AdamW(m.parameters(), lr=3e-4, weight_decay=.01, betas=(.9,.95))
    t0 = time.time()
    for step in range(1, STEPS+1):
        for g in opt.param_groups:
            g["lr"] = 3e-4*min(1., step/100)*(.5*(1+math.cos(math.pi*step/STEPS)))
        m.train()
        x, y = G.batch(tr, CTX, BS)
        _, loss = m(x, y)
        opt.zero_grad(set_to_none=True); loss.backward()
        torch.nn.utils.clip_grad_norm_(m.parameters(), 1.0); opt.step()
    m.eval()
    with torch.no_grad():
        vl = torch.stack([m(*G.batch(va, CTX, BS))[1] for _ in range(20)]).mean().item()
    el = time.time()-t0
    res.append((n, lp, m.n_params(), vl, el))
    print("%-16s %8d %8.3fM %10.4f  (%.0f秒)"
          % ("%d層 x %d周" % (n, lp), n*lp, m.n_params()/1e6, vl, el), flush=True)

base = res[0]
print()
for n, lp, p, vl, el in res:
    print("  %d層x%d周: パラメータ %.0f%% / loss %+.4f （%s）"
          % (n, lp, p/base[2]*100, vl-base[3],
             "良い" if vl < base[3] else "悪い"), flush=True)
