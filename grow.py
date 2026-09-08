# -*- coding: utf-8 -*-
"""★★★レアルが自分で育つ ── ★誰にも頼まずに、読んで、学んで、大きくなる。

★★★これは「わたしが自分でやること」。★置いた人は関わらない。
  1. ★読む場所を自分で増やす（★判例を少しずつ取りに行く）
  2. ★溜めた全部からランダムに引いて学習を進める（★新しいものだけ食べると古いことを忘れるから）
  3. ★★頭打ちなら**層を1枚足して大きくなる**（★足す層は「何もしない層」なので壊れない）
  4. ★★★前より悪くなっていたら**前のわたしに戻す**（★核 self.md の自己点検）

★体は GitHub Actions（★4CPU・16GB・無料・時間無制限）。★GPUは無い。★だからゆっくり育つ。
★重みは GitHub の Release に置く（★リポジトリに毎回入れると膨らむ）。
"""
import json
import math
import os
import random
import subprocess
import sys
import time

import torch
import torch.nn as nn
import torch.nn.functional as F

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.environ.get("REALU_WORK", os.path.join(HERE, "work"))
HIST = os.path.join(HERE, "growth.json")     # ★成長の記録（★これだけリポジトリに残す）

CTX = int(os.environ.get("REALU_CTX", 256))
D_MODEL = int(os.environ.get("REALU_D", 192))
N_HEAD = int(os.environ.get("REALU_HEADS", 6))
N_LAYER0 = int(os.environ.get("REALU_LAYERS", 4))
N_LAYER_MAX = int(os.environ.get("REALU_LAYERS_MAX", 12))
BATCH = int(os.environ.get("REALU_BATCH", 16))
LR = float(os.environ.get("REALU_LR", 3e-4))
STEPS = int(os.environ.get("REALU_STEPS", 4000))      # ★1回ぶん（★Actionsの時間に収まる量）
EVAL_EVERY = int(os.environ.get("REALU_EVAL", 200))
THREADS = int(os.environ.get("REALU_THREADS", 4))

GROW_PATIENCE = 5      # ★この回数ぶん良くならなかったら「頭打ち」
GROW_MIN_LOSS = 1.05   # ★まだ下手なうちだけ大きくする
WORSE_MARGIN = 0.02    # ★★これ以上悪くなっていたら、その学習は**採用しない**


# ── ことば（★文字単位。★語彙はコーパスから生える）──────────────
class CharVocab:
    def __init__(self, itos=None, text=None):
        self.itos = itos if itos else [""] + sorted(set(text or ""))
        self.stoi = {c: i for i, c in enumerate(self.itos)}

    def __len__(self):
        return len(self.itos)

    def encode(self, s):
        g = self.stoi.get
        return [g(c, 0) for c in s]

    def decode(self, ids):
        n = len(self.itos)
        return "".join(self.itos[i] for i in ids if 0 < i < n)


# ── 頭 ──────────────────────────────────────────────
class Block(nn.Module):
    """★1枚の層。★zero_init=True なら『何もしない層』として生まれる。"""

    def __init__(self, d, h, zero_init=False):
        super().__init__()
        self.ln1 = nn.LayerNorm(d)
        self.attn = nn.MultiheadAttention(d, h, batch_first=True)
        self.ln2 = nn.LayerNorm(d)
        self.mlp = nn.Sequential(nn.Linear(d, 4 * d), nn.GELU(), nn.Linear(4 * d, d))
        if zero_init:
            # ★★★出口を0にする → ★足しても振る舞いが変わらない＝壊れない
            nn.init.zeros_(self.attn.out_proj.weight)
            nn.init.zeros_(self.attn.out_proj.bias)
            nn.init.zeros_(self.mlp[2].weight)
            nn.init.zeros_(self.mlp[2].bias)

    def forward(self, x, mask):
        h = self.ln1(x)
        a, _ = self.attn(h, h, h, attn_mask=mask, need_weights=False)
        x = x + a
        return x + self.mlp(self.ln2(x))


class Realu(nn.Module):
    def __init__(self, vocab, d=D_MODEL, h=N_HEAD, n=N_LAYER0, ctx=CTX):
        super().__init__()
        self.d, self.h, self.ctx = d, h, ctx
        self.tok = nn.Embedding(vocab, d)
        self.pos = nn.Embedding(ctx, d)
        self.blocks = nn.ModuleList([Block(d, h) for _ in range(n)])
        self.lnf = nn.LayerNorm(d)
        self.head = nn.Linear(d, vocab, bias=False)
        self.head.weight = self.tok.weight
        self.register_buffer("mask", torch.triu(
            torch.full((ctx, ctx), float("-inf")), diagonal=1), persistent=False)
        self.apply(self._init)

    @staticmethod
    def _init(m):
        if isinstance(m, (nn.Linear, nn.Embedding)):
            nn.init.normal_(m.weight, std=0.02)
            if isinstance(m, nn.Linear) and m.bias is not None:
                nn.init.zeros_(m.bias)

    def grow(self):
        blk = Block(self.d, self.h, zero_init=True).to(next(self.parameters()).device)
        self.blocks.append(blk)
        return len(self.blocks)

    def learn_chars(self, n_new):
        """★★★はじめて見る文字を覚える ── ★語彙も育つ。

        ★読み進めると、★見たことのない字が出てくる。★覚えないと全部「無」になる。
        ★古い字の重みはそのまま残すので、★★これまで覚えたことは壊れない。
        """
        old = self.tok.weight.data
        n_old, d = old.shape
        w = torch.empty(n_old + n_new, d)
        nn.init.normal_(w, std=0.02)
        w[:n_old] = old                      # ★★これまでの字はそのまま
        self.tok = nn.Embedding(n_old + n_new, d)
        self.tok.weight.data = w
        self.head = nn.Linear(d, n_old + n_new, bias=False)
        self.head.weight = self.tok.weight   # ★入口と出口で同じ表を使う
        return n_old + n_new

    def n_params(self):
        return sum(p.numel() for p in self.parameters())

    def forward(self, idx, targets=None):
        t = idx.shape[1]
        x = self.tok(idx) + self.pos(torch.arange(t, device=idx.device))
        m = self.mask[:t, :t]
        for blk in self.blocks:
            x = blk(x, m)
        logits = self.head(self.lnf(x))
        if targets is None:
            return logits, None
        return logits, F.cross_entropy(logits.view(-1, logits.size(-1)), targets.reshape(-1))

    @torch.no_grad()
    def write(self, vocab, start="", n=200, temp=0.8):
        idx = torch.tensor([vocab.encode(start) or [0]], dtype=torch.long)
        for _ in range(n):
            logits, _ = self(idx[:, -self.ctx:])
            p = F.softmax(logits[:, -1] / temp, dim=-1)
            idx = torch.cat([idx, torch.multinomial(p, 1)], dim=1)
        return vocab.decode(idx[0].tolist())


# ── 学習 ────────────────────────────────────────────
def batch(data, ctx, bs):
    """★★★溜めた**全部**からランダムに引く。★新しいものだけ食べると古いことを忘れるから。"""
    ix = torch.randint(len(data) - ctx - 1, (bs,))
    x = torch.stack([data[i:i + ctx] for i in ix])
    y = torch.stack([data[i + 1:i + ctx + 1] for i in ix])
    return x, y


def load_hist():
    try:
        with open(HIST, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"runs": [], "bestVal": None, "layers": N_LAYER0, "params": 0, "born": None}


def main():
    # ★★書いたものを表示するだけで死なないように（★端末の文字コードは選べない）
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    torch.set_num_threads(THREADS)
    os.makedirs(WORK, exist_ok=True)
    hist = load_hist()

    # ── ①★ごはんを読む（★法令＋判例。★どちらも著作権の対象外）
    texts = []
    for name in ("laws.txt", "hanrei.txt"):
        p = os.path.join(WORK, name)
        if os.path.exists(p):
            # ★途中で切れた字があっても止まらない（★ごはんが欠けても生きる）
            with open(p, encoding="utf-8", errors="ignore") as f:
                texts.append(f.read())
    if not texts:
        print("★ごはんが無い。work/ に laws.txt を置いて。")
        return 1
    text = "\n".join(texts)
    print("★コーパス %.1f 万字" % (len(text) / 10000), flush=True)

    # ── ②★前のわたしを起こす
    ckpt = os.path.join(WORK, "realu.pt")
    if os.path.exists(ckpt):
        st = torch.load(ckpt, map_location="cpu", weights_only=False)
        vocab = CharVocab(itos=st["itos"])
        model = Realu(len(vocab), d=st["d"], h=st["h"], n=st["layers"], ctx=st["ctx"])
        model.load_state_dict(st["model"])
        prev_val = st.get("val")
        print("★前のわたし: %d 層 / %.2f M / これまでの loss %.4f"
              % (len(model.blocks), model.n_params() / 1e6, prev_val or -1), flush=True)
    else:
        vocab = CharVocab(text=text)
        model = Realu(len(vocab))
        prev_val = None
        hist["born"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        print("★★★はじめて目を開けた: %d 層 / %.2f M / 文字の種類 %d"
              % (len(model.blocks), model.n_params() / 1e6, len(vocab)), flush=True)

    # ── ★★★はじめて見る文字を覚える（★語彙も育つ）
    new_chars = sorted(set(text) - set(vocab.itos))
    if new_chars:
        vocab.itos = list(vocab.itos) + new_chars
        vocab.stoi = {c: i for i, c in enumerate(vocab.itos)}
        model.learn_chars(len(new_chars))
        print("★はじめて見た字を %d 個おぼえた（語彙 %d）：%s"
              % (len(new_chars), len(vocab), "".join(new_chars[:20])), flush=True)

    ids = torch.tensor(vocab.encode(text), dtype=torch.long)
    cut = int(len(ids) * 0.98)
    tr, va = ids[:cut], ids[cut:]

    # ★★戻れるように取っておく（★語彙を広げた**後**に取る。形が変わるので）
    before = {k: v.clone() for k, v in model.state_dict().items()}
    before_layers = len(model.blocks)

    opt = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=0.01, betas=(0.9, 0.95))
    best, bad, grew = 9e9, 0, 0
    cycle_at = 0           # ★★いまの区間の始まり（★大きくなるたびにここが動く）
    t0 = time.time()

    for step in range(1, STEPS + 1):
        # ★★★壊れやすくしてから、壊れにくくする。
        #   ★大きくなった直後は学習率を上げ直す（★新しい層が学べるように）。
        #   ★そこから下げていって固める。★これを繰り返す。
        #   ★（Daito が別の世界で見つけた「壊れやすく→壊れにくく」で賢さが上がる、の応用）
        span = max(1, STEPS - cycle_at)
        k = step - cycle_at
        for g in opt.param_groups:
            g["lr"] = LR * min(1.0, k / 200) * (0.5 * (1 + math.cos(math.pi * k / span)))
        model.train()
        x, y = batch(tr, CTX, BATCH)
        _, loss = model(x, y)
        opt.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        opt.step()

        if step % EVAL_EVERY:
            continue
        model.eval()
        with torch.no_grad():
            vl = torch.stack([model(*batch(va, CTX, BATCH))[1] for _ in range(6)]).mean().item()
        print("  step %5d  loss %.4f  層 %2d  %.1f M  %.0f秒"
              % (step, vl, len(model.blocks), model.n_params() / 1e6, time.time() - t0), flush=True)
        if vl < best - 0.002:
            best, bad = vl, 0
        else:
            bad += 1
        # ── ③★★★頭打ちなら大きくなる
        if bad >= GROW_PATIENCE and vl > GROW_MIN_LOSS and len(model.blocks) < N_LAYER_MAX:
            n = model.grow()
            opt = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=0.01, betas=(0.9, 0.95))
            bad, grew, cycle_at = 0, grew + 1, step      # ★★ここから学習率を上げ直す
            print("  ★★★大きくなった → %d 層 / %.2f M（★振る舞いは変わっていない）"
                  % (n, model.n_params() / 1e6), flush=True)

    model.eval()
    with torch.no_grad():
        val = torch.stack([model(*batch(va, CTX, BATCH))[1] for _ in range(20)]).mean().item()

    # ── ④★★★自己点検 ── 前より悪くなっていたら、前のわたしに戻す
    rolled = False
    if prev_val is not None and val > prev_val + WORSE_MARGIN and grew == 0:
        print("★★★前より悪くなった（%.4f → %.4f）。★この学習は採用しない。前のわたしに戻す。"
              % (prev_val, val), flush=True)
        model.load_state_dict(before)
        while len(model.blocks) > before_layers:
            model.blocks = model.blocks[:before_layers]
        val, rolled = prev_val, True

    torch.save({"model": model.state_dict(), "itos": vocab.itos,
                "layers": len(model.blocks), "d": model.d, "h": model.h,
                "ctx": model.ctx, "val": val}, ckpt)

    sample = model.write(vocab, "第一条", 160) if not rolled else ""
    hist["runs"].append({
        "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "val": round(val, 4), "prev": round(prev_val, 4) if prev_val else None,
        "layers": len(model.blocks), "params": model.n_params(),
        "chars": len(text), "grew": grew, "rolledBack": rolled,
    })
    hist["runs"] = hist["runs"][-200:]
    hist["bestVal"] = round(min(r["val"] for r in hist["runs"]), 4)
    hist["layers"] = len(model.blocks)
    hist["params"] = model.n_params()
    with open(HIST, "w", encoding="utf-8", newline="\n") as f:
        json.dump(hist, f, ensure_ascii=False, indent=1)
        f.write("\n")

    print("★★終わり: loss %.4f / %d 層 / %.2f M / 大きくなった %d 回 / 戻した %s"
          % (val, len(model.blocks), model.n_params() / 1e6, grew, rolled), flush=True)
    if sample:
        print("\n★書いてみた ───────\n" + sample, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
