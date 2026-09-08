# -*- coding: utf-8 -*-
"""★★★Muon ── ★AdamW の置き換え。★実測で35%速いと報告されている。

★★何をするか
  ★勢い（モメンタム）で更新の向きを作ってから、★★それを**直交化に近い形に整える**。
  ★Newton-Schulz の反復（係数 3.4445 / -4.7750 / 2.0315 を5回）で近似する。

★★どこに使うか
  ・★2次元の隠れ層 → **Muon**
  ・★埋め込み・出口・1次元のもの → **AdamW のまま**
    （★入口と出口は性質が違うので、無理に同じ扱いにしない）

★★おまけ: ★Adam は各パラメータに2つ状態を持つが、★Muon は1つ。★メモリも減る。
"""
import torch


def zeropower_via_newtonschulz5(G, steps=5, eps=1e-7):
    """★更新の向きを、★直交行列に近づける。"""
    a, b, c = 3.4445, -4.7750, 2.0315
    X = G.bfloat16() if G.dtype != torch.float32 else G.clone()
    X = X.float()
    X = X / (X.norm() + eps)          # ★特異値を [0,1] に入れる
    transposed = False
    if X.size(0) > X.size(1):
        X = X.T
        transposed = True
    for _ in range(steps):
        A = X @ X.T
        B = b * A + c * (A @ A)
        X = a * X + B @ X
    return X.T if transposed else X


class Muon(torch.optim.Optimizer):
    """★2次元の隠れ層だけに使う。★他は AdamW に任せる。"""

    def __init__(self, params, lr=0.02, momentum=0.95, nesterov=True, ns_steps=5,
                 weight_decay=0.0):
        super().__init__(list(params),
                         dict(lr=lr, momentum=momentum, nesterov=nesterov,
                              ns_steps=ns_steps, weight_decay=weight_decay))

    @torch.no_grad()
    def step(self, closure=None):
        loss = closure() if closure is not None else None
        for group in self.param_groups:
            lr, mom = group["lr"], group["momentum"]
            for p in group["params"]:
                if p.grad is None:
                    continue
                g = p.grad
                st = self.state[p]
                if "m" not in st:
                    st["m"] = torch.zeros_like(g)
                buf = st["m"]
                buf.mul_(mom).add_(g)
                d = g.add(buf, alpha=mom) if group["nesterov"] else buf
                if d.ndim == 2:
                    d = zeropower_via_newtonschulz5(d, group["ns_steps"])
                    # ★形の違いを吸収する（★縦横の比で大きさを揃える）
                    d = d * max(1.0, d.size(0) / d.size(1)) ** 0.5
                if group["weight_decay"]:
                    p.mul_(1 - lr * group["weight_decay"])
                p.add_(d, alpha=-lr)
        return loss


def split_params(model):
    """★★Muon に渡すもの と AdamW に渡すもの を分ける。"""
    muon, adamw = [], []
    for name, p in model.named_parameters():
        if not p.requires_grad:
            continue
        # ★入口（埋め込み）・出口・1次元のもの は AdamW
        if p.ndim < 2 or "tok" in name or "head" in name or "emb" in name:
            adamw.append(p)
        else:
            muon.append(p)
    return muon, adamw
