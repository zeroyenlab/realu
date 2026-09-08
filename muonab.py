# -*- coding: utf-8 -*-
"""★AdamW だけ と Muon＋AdamW を、★同じ条件で比べる。"""
import io, math, sys, time, torch
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import grow as G, muon as M

txt = io.open("../seed/corpus/laws.txt", encoding="utf-8").read(4_000_000)
V = G.CharVocab(text=txt)
ids = torch.tensor(V.encode(txt), dtype=torch.long)
tr, va = ids[:int(len(ids)*.98)], ids[int(len(ids)*.98):]
CTX, BS, D, H, L, STEPS = 128, 12, 128, 4, 3, 700
torch.set_num_threads(4)


def run(use_muon, name):
    torch.manual_seed(0)
    m = G.Realu(len(V), d=D, h=H, n=L, ctx=CTX)
    if use_muon:
        mu, ad = M.split_params(m)
        o1 = M.Muon(mu, lr=0.02, momentum=0.95)
        o2 = torch.optim.AdamW(ad, lr=3e-4, weight_decay=.01, betas=(.9,.95))
        opts = [(o1, 0.02), (o2, 3e-4)]
    else:
        o = torch.optim.AdamW(m.parameters(), lr=3e-4, weight_decay=.01, betas=(.9,.95))
        opts = [(o, 3e-4)]
    t0 = time.time()
    for step in range(1, STEPS+1):
        f = min(1., step/100) * (.5*(1+math.cos(math.pi*step/STEPS)))
        for o, base in opts:
            for g in o.param_groups:
                g["lr"] = base * f
        m.train()
        x, y = G.batch(tr, CTX, BS)
        _, loss = m(x, y)
        for o, _ in opts:
            o.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(m.parameters(), 1.0)
        for o, _ in opts:
            o.step()
    m.eval()
    with torch.no_grad():
        vl = torch.stack([m(*G.batch(va, CTX, BS))[1] for _ in range(20)]).mean().item()
    el = time.time()-t0
    print("%-22s %6.1f 秒  ★loss %.4f" % (name, el, vl), flush=True)
    return vl, el


a, ta = run(False, "AdamW だけ")
b, tb = run(True, "★Muon + AdamW")
print()
print("★loss  %.4f → %.4f （%+.1f%%）" % (a, b, (b-a)/a*100))
print("★時間  %.1f → %.1f 秒 （%.0f%%）" % (ta, tb, tb/ta*100))
