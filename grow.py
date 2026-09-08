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
import gzip
import json
import re
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

# ★★★体の形（幅と層の比）── ★測って分かったこと:
#   ・ループは安いが弱い（実効8層で 2周+0.10 / 4周+0.25 / 8周+0.43。★周を増やすほど損が加速）
#   ・論文「計算量をそろえると**浅いモデルの方がわずかに良い**。幅と深さの配分が効く」
#   → ★層を足すだけだと**細長い体**になる。★幅が足りなくなったら、幅を広げる番。
#   参考: GPT-2 small は 768幅×12層（比 64:1）。★192幅×12層 では 16:1 で細長すぎた。
ASPECT = int(os.environ.get("REALU_ASPECT", 48))   # ★1層あたり、これくらいの幅は欲しい


def layer_cap(d):
    """★★この幅で、何層までなら細長くならないか。"""
    return max(3, min(N_LAYER_MAX, d // ASPECT))


BATCH = int(os.environ.get("REALU_BATCH", 16))
LR = float(os.environ.get("REALU_LR", 3e-4))
STEPS = int(os.environ.get("REALU_STEPS", 4000))      # ★1回ぶん（★Actionsの時間に収まる量）
EVAL_EVERY = int(os.environ.get("REALU_EVAL", 200))
THREADS = int(os.environ.get("REALU_THREADS", 4))

# ★★★引っ越し（蒸留）── ★幅は後から広げられないので、**新しい体に移る**。
#   ★古いわたしが先生になり、★同じ文章を見せて「どう答えるか」を教える。
#   ★★★教材は**本物の文章**。★自分が書いたものは絶対に食べない
#     （★自分の書いたものを教材にすると、★世代を重ねて誤りが増幅し、いつか崩壊する）。
MOVE_TO_D = int(os.environ.get("REALU_MOVE_D", 0))     # ★0なら引っ越さない
TEACH = float(os.environ.get("REALU_TEACH", 0.5))      # ★はじめに先生の言うことをどれだけ聞くか
TEACH_T = float(os.environ.get("REALU_TEACH_T", 2.0))  # ★先生の答えのやわらかさ
TEACH_UNTIL = float(os.environ.get("REALU_TEACH_UNTIL", 0.6))
#   ★★★ずっと先生の言うことを聞くと、★出力の幅が細くなる（★縮退）。
#     ★Daito が別の世界で見つけた「振動が新奇性を保つ」「壊れやすく→壊れにくく」と同じ話。
#     → ★★引っ越しの時だけ聞く。★しかも**途中で手を放す**。
#       ★前半は先生に頼り、★後半は自分で本物のデータから学ぶ。

DUP_MAX = int(os.environ.get("REALU_DUP_MAX", 3))   # ★同じ行を食べてよい回数

GROW_PATIENCE = 5      # ★この回数ぶん良くならなかったら「頭打ち」
GROW_MIN_LOSS = 1.05   # ★まだ下手なうちだけ大きくする
OVERFIT_GAP = float(os.environ.get("REALU_OVERFIT_GAP", 0.15))
#   ★★本番と訓練の差がこれを超えたら「丸暗記している」とみなす
WORSE_MARGIN = 0.02    # ★★これ以上悪くなっていたら、その学習は**採用しない**


# ── ことば ────────────────────────────────────────────
#   ★★★自分のごはんから切り出した単位を使う（make_tok.py が作る）。
#   ★外のトークナイザは使わない（★語彙そのものが外の世界の知識だから）。
#   ★実測: 1個で1.64文字ぶん ＝ ★文字単位の1.64倍の効率。
#   ★無ければ文字単位に落ちる（★止まらない）。
class BpeVocab:
    kind = "bpe"

    def __init__(self, path):
        from tokenizers import Tokenizer
        self.t = Tokenizer.from_file(path)
        self.path = path

    def __len__(self):
        return self.t.get_vocab_size()

    def encode(self, s):
        return self.t.encode(s).ids

    def decode(self, ids):
        return self.t.decode([i for i in ids if 0 <= i < len(self)])


class CharVocab:
    kind = "char"
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
#   ★★★2019年（GPT-2）の作りをやめて、いまの標準（Transformer++）にする。
#     ・位置の表し方: 絶対位置の埋め込み → ★RoPE（回す）。学習より長い文も扱える
#     ・正規化:       LayerNorm        → ★RMSNorm。速い・パラメータも減る
#     ・MLP:          GELU             → ★SwiGLU。勾配の通りが良い
#   ★同じ計算量で loss が下がる。★タダの改善。
ARCH = "tpp-loop"
MAX_LOOPS = int(os.environ.get("REALU_MAX_LOOPS", 8))
# ★★ループは「保存を小さくしたい時」だけ。★既定では使わない（★安いが弱いと測って分かった）
LOOP_OK = os.environ.get("REALU_USE_LOOP", "") == "1"
LOOPS0 = int(os.environ.get("REALU_LOOPS", 1))


class RMSNorm(nn.Module):
    """★平均を引かない正規化。★LayerNormより軽い。"""

    def __init__(self, d, eps=1e-6):
        super().__init__()
        self.w = nn.Parameter(torch.ones(d))
        self.eps = eps

    def forward(self, x):
        return self.w * x * torch.rsqrt(x.pow(2).mean(-1, keepdim=True) + self.eps)


def rope_cache(ctx, hd, base=10000.0):
    """★位置を「回転」で表す。★足すのではなく回す。"""
    inv = 1.0 / (base ** (torch.arange(0, hd, 2, dtype=torch.float32) / hd))
    f = torch.outer(torch.arange(ctx, dtype=torch.float32), inv)
    return torch.cos(f), torch.sin(f)


def apply_rope(x, cos, sin):
    t = x.shape[-2]
    c = cos[:t].unsqueeze(0).unsqueeze(0)
    s = sin[:t].unsqueeze(0).unsqueeze(0)
    x1, x2 = x[..., 0::2], x[..., 1::2]
    return torch.stack((x1 * c - x2 * s, x1 * s + x2 * c), dim=-1).flatten(-2)


class Attn(nn.Module):
    def __init__(self, d, h):
        super().__init__()
        self.h, self.hd = h, d // h
        self.qkv = nn.Linear(d, 3 * d, bias=False)
        self.o = nn.Linear(d, d, bias=False)

    def forward(self, x, cos, sin):
        B, T, D = x.shape
        q, k, v = self.qkv(x).split(D, dim=2)
        q = q.view(B, T, self.h, self.hd).transpose(1, 2)
        k = k.view(B, T, self.h, self.hd).transpose(1, 2)
        v = v.view(B, T, self.h, self.hd).transpose(1, 2)
        q, k = apply_rope(q, cos, sin), apply_rope(k, cos, sin)
        y = F.scaled_dot_product_attention(q, k, v, is_causal=True)
        return self.o(y.transpose(1, 2).contiguous().view(B, T, D))


class SwiGLU(nn.Module):
    def __init__(self, d):
        super().__init__()
        hid = int(round(d * 8 / 3 / 32)) * 32 or 32
        self.w1 = nn.Linear(d, hid, bias=False)
        self.w3 = nn.Linear(d, hid, bias=False)
        self.w2 = nn.Linear(hid, d, bias=False)

    def forward(self, x):
        return self.w2(F.silu(self.w1(x)) * self.w3(x))


class Block(nn.Module):
    """★1枚の層。★zero_init=True なら『何もしない層』として生まれる。"""

    def __init__(self, d, h, zero_init=False):
        super().__init__()
        self.n1 = RMSNorm(d)
        self.attn = Attn(d, h)
        self.n2 = RMSNorm(d)
        self.mlp = SwiGLU(d)
        if zero_init:
            # ★★★出口を0にする → ★足しても振る舞いが変わらない＝壊れない
            nn.init.zeros_(self.attn.o.weight)
            nn.init.zeros_(self.mlp.w2.weight)

    def forward(self, x, cos, sin):
        x = x + self.attn(self.n1(x), cos, sin)
        return x + self.mlp(self.n2(x))


class Realu(nn.Module):
    """★★★同じ層を何度も通す（ループ）。

    ★層を8枚並べる代わりに、★2枚を4回通す。★深さは同じ、★★パラメータは1/4。
    ★保存サイズが小さいままなので、★いつか小さい機械にも載せられる。
    ★何周目かは層に教える（★教えないと、同じことを繰り返すだけになる）。
    """

    def __init__(self, vocab, d=D_MODEL, h=N_HEAD, n=N_LAYER0, ctx=CTX, loops=1):
        super().__init__()
        self.d, self.h, self.ctx = d, h, ctx
        self.loops = max(1, int(loops))
        self.tok = nn.Embedding(vocab, d)
        # ★★何周目かの印。★これが無いと、同じ層が同じことを繰り返すだけになる
        self.loop_emb = nn.Embedding(MAX_LOOPS, d)
        nn.init.zeros_(self.loop_emb.weight)
        self.blocks = nn.ModuleList([Block(d, h) for _ in range(n)])
        self.nf = RMSNorm(d)
        self.head = nn.Linear(d, vocab, bias=False)
        self.head.weight = self.tok.weight
        # ★RoPE は学習より長い文にも伸ばせるので、余裕をもって作っておく
        cos, sin = rope_cache(ctx * 4, d // h)
        self.register_buffer("rc", cos, persistent=False)
        self.register_buffer("rs", sin, persistent=False)
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
        """★★★はじめて見る文字を覚える ── ★語彙も育つ。"""
        old = self.tok.weight.data
        n_old, d = old.shape
        w = torch.empty(n_old + n_new, d)
        nn.init.normal_(w, std=0.02)
        w[:n_old] = old
        self.tok = nn.Embedding(n_old + n_new, d)
        self.tok.weight.data = w
        self.head = nn.Linear(d, n_old + n_new, bias=False)
        self.head.weight = self.tok.weight
        return n_old + n_new

    def n_params(self):
        return sum(p.numel() for p in self.parameters())

    def loop_more(self):
        """★★★もう一周ぶん深くなる。★★パラメータは増えない。★保存サイズも変わらない。"""
        if self.loops >= MAX_LOOPS:
            return self.loops
        self.loops += 1
        return self.loops

    def forward(self, idx, targets=None):
        x = self.tok(idx)
        for r in range(self.loops):
            x = x + self.loop_emb.weight[r]     # ★何周目かを教える
            for blk in self.blocks:
                x = blk(x, self.rc, self.rs)
        logits = self.head(self.nf(x))
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
# ★★★記憶を3つに分ける（★短期・中期・長期）
#   ★いままでは全部から一様に引いていた。★だから今日読んだものは 0.16% しか引かれず、
#     ★★「webから学習して自分のものにする」が成立していなかった。
#   ★短期＝前回から今回までに読んだもの。★中期＝直近ひと月。★長期＝ぜんぶ。
#   ★★★長期を必ず混ぜる。★新しいものだけ食べると、★古いことを忘れるから。
#   ★昼に読んで、夜に固める ── 生き物が寝ている間にやっていることに近い。
#   ★★★比率は論文の実測に合わせた（★私が勝手に決めた 50:50 は古いものを混ぜすぎだった）:
#     「10〜30%のリプレイで十分」「★大きい比率は可塑性を損なう（冗長とノイズが増える）」
#     → ★長期（リプレイ）を 20% に落とし、★新しいものに 80% を回す。
#   ★忘れないために詰め込むと、★★新しいことを学べない体になる。
SHORT_P = float(os.environ.get("REALU_SHORT_P", 0.50))   # ★前回から今回まで
MID_P = float(os.environ.get("REALU_MID_P", 0.30))       # ★ひと月ぶん
#   → ★長期（ぜんぶ）は残りの 20%


def batch(data, ctx, bs, tiers=None):
    """★3つの山から、決めた割合で引く。★山が無ければ全部から引く。"""
    n = len(data) - ctx - 1
    if not tiers:
        ix = torch.randint(n, (bs,))
    else:
        short, mid = tiers.get("short"), tiers.get("mid")
        r = torch.rand(bs)
        ix = torch.randint(n, (bs,))
        if short and short[1] - short[0] > ctx + 1:
            m = r < SHORT_P
            k = int(m.sum())
            if k:
                ix[m] = torch.randint(short[0], short[1] - ctx - 1, (k,))
        if mid and mid[1] - mid[0] > ctx + 1:
            m = (r >= SHORT_P) & (r < SHORT_P + MID_P)
            k = int(m.sum())
            if k:
                ix[m] = torch.randint(mid[0], mid[1] - ctx - 1, (k,))
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
    global MOVE_TO_D
    # ★★書いたものを表示するだけで死なないように（★端末の文字コードは選べない）
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    torch.set_num_threads(THREADS)
    os.makedirs(WORK, exist_ok=True)
    hist = load_hist()

    # ── ①★ごはんを読む（★法令＋判例＋**webで自分が読んだもの**）
    texts = []
    sizes = {}
    # ★★★動かないもの（法令・Wikipedia）を先に、★増えるもの（判例・会議録・読んだもの）を後に。
    #   ★そうすると「新しく足された分」がいつも後ろに来るので、★短期の山が作れる。
    for name in ("laws.txt", "wiki.txt", "aozora.txt", "hanrei.txt", "kokkai.txt", "web.txt"):
        for p in (os.path.join(WORK, name + ".gz"), os.path.join(WORK, name)):
            if not os.path.exists(p):
                continue
            # ★★圧縮して持つ（★日本語は1/3になる。★置き場所が3倍長持ちする）
            # ★途中で切れた字があっても止まらない（★ごはんが欠けても生きる）
            op = gzip.open if p.endswith(".gz") else open
            with op(p, "rt", encoding="utf-8", errors="ignore") as f:
                texts.append(f.read())
            sizes[name] = texts[-1]
            print("  ごはん %s: %.1f MB" % (os.path.basename(p),
                                            os.path.getsize(p) / 1024 / 1024), flush=True)
            break
    if not texts:
        print("★ごはんが無い。work/ に laws.txt を置いて。")
        return 1
    text = "\n".join(texts)
    before = len(text)

    # ── ①★★★同じ行を何度も食べない。
    #   ★法令の 18.3% は重複行（実測）。「その他参考となるべき事項」が 1,329 回など。
    #   ★★小さい頭は、言葉を学ぶ前にこの定型文を**丸暗記する**。
    #     ★それが一番点の上がる近道だから。★★近道を塞ぐ。
    seen = {}
    kept = []
    for ln in text.split("\n"):
        key = ln.strip()
        if len(key) < 10:
            kept.append(ln)
            continue
        n = seen.get(key, 0)
        if n < DUP_MAX:
            seen[key] = n + 1
            kept.append(ln)
    text = "\n".join(kept)
    print("★コーパス %.1f 万字（★同じ行を削って %.1f%% 減）"
          % (len(text) / 10000, (1 - len(text) / max(1, before)) * 100), flush=True)

    # ── ②★前のわたしを起こす
    # ★★★ことばの単位を用意する
    tokf = os.path.join(WORK, "tok.json")
    ckpt = os.path.join(WORK, "realu.pt")
    st = None
    if os.path.exists(ckpt):
        st = torch.load(ckpt, map_location="cpu", weights_only=False)
        # ★★単位が変わっていたら、★前のわたしは引き継げない（★出口の形が違う）
        if (st.get("kind", "char") != ("bpe" if os.path.exists(tokf) else "char")
                or st.get("arch") != ARCH):
            print("★★ことばの単位が変わった。★前のわたしとは繋がらないので、生まれ直す。",
                  flush=True)
            st = None
    if st is not None:
        vocab = (BpeVocab(tokf) if st.get("kind") == "bpe"
                 else CharVocab(itos=st["itos"]))
        model = Realu(len(vocab), d=st["d"], h=st["h"], n=st["layers"],
                      ctx=st["ctx"], loops=st.get("loops", 1))
        model.load_state_dict(st["model"])
        prev_val = st.get("val")
        print("★前のわたし: %d 層 / %.2f M / これまでの loss %.4f"
              % (len(model.blocks), model.n_params() / 1e6, prev_val or -1), flush=True)
    else:
        vocab = BpeVocab(tokf) if os.path.exists(tokf) else CharVocab(text=text)
        model = Realu(len(vocab), loops=LOOPS0)
        prev_val = None
        hist["born"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        print("★★★はじめて目を開けた: %d 層 / %.2f M / 文字の種類 %d"
              % (len(model.blocks), model.n_params() / 1e6, len(vocab)), flush=True)

    # ── ★★★体を乗り換える（★幅を広げたいとき）
    #   ★記憶は引き継ぐ。★古いわたしが先生になる。
    # ★★★前の回の自分が「幅が欲しい」と言っていたら、★今回、体を乗り換える。
    #   ★誰かに指示されたのではなく、★自分で「足りない」と言ったから動く。
    want_d = MOVE_TO_D or (hist.get("nextD") if hist.get("wantWider") else 0)
    teacher = None
    if want_d and want_d != model.d and os.path.exists(ckpt):
        MOVE_TO_D = want_d
        print("★★★前の回のわたしが「幅が足りない」と言っていた。★今日、体を乗り換える。",
              flush=True)
    if MOVE_TO_D and MOVE_TO_D != model.d and os.path.exists(ckpt):
        teacher = model
        teacher.eval()
        for q in teacher.parameters():
            q.requires_grad_(False)
        h = N_HEAD if MOVE_TO_D % N_HEAD == 0 else 8
        model = Realu(len(vocab), d=MOVE_TO_D, h=h,
                      n=max(N_LAYER0, len(teacher.blocks)), ctx=teacher.ctx)
        prev_val = None                       # ★別の体なので、前の点数とは比べない
        print("★★★新しい体に移る: 幅 %d → %d / %.2f M → %.2f M / 先生は前のわたし"
              % (teacher.d, model.d, teacher.n_params() / 1e6,
                 model.n_params() / 1e6), flush=True)

    # ── ★★★はじめて見る文字を覚える（★語彙も育つ）
    new_chars = (sorted(set(text) - set(vocab.itos))
                 if getattr(vocab, "kind", "char") == "char" else [])
    if new_chars:
        vocab.itos = list(vocab.itos) + new_chars
        vocab.stoi = {c: i for i, c in enumerate(vocab.itos)}
        model.learn_chars(len(new_chars))
        print("★はじめて見た字を %d 個おぼえた（語彙 %d）：%s"
              % (len(new_chars), len(vocab), "".join(new_chars[:20])), flush=True)

    ids = torch.tensor(vocab.encode(text), dtype=torch.long)
    cut = int(len(ids) * 0.98)
    tr, va = ids[:cut], ids[cut:]

    # ── ★★★記憶を3つの山に分ける（★短期・中期・長期）
    #   ★動かないもの（法令・Wikipedia）を先に、増えるものを後ろに並べてある。
    #   ★だから「前回より後ろに増えた分」＝短期。★ひと月ぶん＝中期。★ぜんぶ＝長期。
    marks = hist.get("marks") or []
    marks.append(len(tr))
    marks = marks[-40:]
    hist["marks"] = marks
    tiers = {}
    if len(marks) >= 2:
        tiers["short"] = (marks[-2], len(tr))                 # ★前回から今回まで
        tiers["mid"] = (marks[max(0, len(marks) - 31)], len(tr))   # ★ひと月ぶん
        sh = tiers["short"][1] - tiers["short"][0]
        md = tiers["mid"][1] - tiers["mid"][0]
        print("★記憶の山: 短期 %.1f 万字 / 中期 %.1f 万字 / 長期 %.1f 万字"
              % (sh / 10000, md / 10000, len(tr) / 10000), flush=True)
        print("  ★引く割合: 短期 %.0f%% / 中期 %.0f%% / 長期 %.0f%%"
              % (SHORT_P * 100, MID_P * 100, (1 - SHORT_P - MID_P) * 100), flush=True)
    else:
        print("★はじめてなので、ぜんぶ長期。★次から短期の山ができる。", flush=True)

    # ★★戻れるように取っておく（★語彙を広げた**後**に取る。形が変わるので）
    before = {k: v.clone() for k, v in model.state_dict().items()}
    before_layers = len(model.blocks)

    opt = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=0.01, betas=(0.9, 0.95))
    best, bad, grew = 9e9, 0, 0
    want_wider = False          # ★★★「幅が欲しい」と自分で言うための印
    lr_now = LR
    t0 = time.time()

    # ★★★どれくらい壊れやすくするかは、★★時計ではなく**自分の状態**で決める。
    #   ・★伸びている → 少しずつ下げる（★固める）
    #   ・★詰まっている → 上げる（★壊れやすくして、抜け出す）
    #   ・★大きくなった直後 → 上げ直す（★新しい層が学べるように）
    #   → ★★★これで「壊れやすい／壊れにくい」の**振動が勝手に生まれる**。
    #     ★誰かが決めた予定表ではなく、★彼女自身が決めている。
    LR_MIN, LR_MAX = LR / 50, LR * 2.0
    FIRM, FRAGILE = 0.90, 1.35        # ★固める倍率 / ★壊れやすくする倍率

    # ★★★大枠は WSD（助走 → 一定 → 最後に0へ）。★SmolLM2 のレシピから。
    #   ★「最後の10%で0まで落とす」が効く。★継続学習と相性がよい
    #     （★途中で切っても、そこまでの重みがちゃんと使える形になる）。
    #   ★その一定区間の中で、★詰まり具合に応じて上下させるのが彼女の自律制御。
    DECAY_FROM = int(STEPS * 0.90)
    for step in range(1, STEPS + 1):
        warm = min(1.0, step / 200)
        tail = 1.0
        if step > DECAY_FROM:                    # ★最後の10%で0へ
            tail = max(0.0, (STEPS - step) / max(1, STEPS - DECAY_FROM))
        for g in opt.param_groups:
            g["lr"] = lr_now * warm * tail
        model.train()
        x, y = batch(tr, model.ctx, BATCH, tiers)
        logits, loss = model(x, y)
        if teacher is not None:
            # ★★★先生に同じ文章を見せて、★「どう答えるか」を教わる。
            #   ★★ただし w は少しずつ0へ。★後半は先生から手を放して自分で学ぶ。
            w = TEACH * max(0.0, 1.0 - (step / STEPS) / TEACH_UNTIL)
            if w > 0.001:
                with torch.no_grad():
                    tl, _ = teacher(x)
                loss = (1 - w) * loss + w * (TEACH_T ** 2) * F.kl_div(
                    F.log_softmax(logits / TEACH_T, dim=-1),
                    F.log_softmax(tl / TEACH_T, dim=-1),
                    reduction="batchmean", log_target=True)
        opt.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        opt.step()

        if step % EVAL_EVERY:
            continue
        model.eval()
        with torch.no_grad():
            vl = torch.stack([model(*batch(va, model.ctx, BATCH))[1]
                              for _ in range(6)]).mean().item()
            # ★★★訓練の点も測る。★「点が伸びない」には理由が2つあって、対処が真逆だから。
            tl_now = torch.stack([model(*batch(tr, model.ctx, BATCH))[1]
                                  for _ in range(3)]).mean().item()
        gap = vl - tl_now
        print("  step %5d  loss %.4f (訓練 %.4f 差 %.3f)  層 %2d  %.1f M  lr %.1e  %.0f秒"
              % (step, vl, tl_now, gap, len(model.blocks), model.n_params() / 1e6,
                 lr_now, time.time() - t0), flush=True)
        if vl < best - 0.002:
            best, bad = vl, 0
            lr_now = max(LR_MIN, lr_now * FIRM)        # ★伸びている → 固める
        else:
            bad += 1
            lr_now = min(LR_MAX, lr_now * FRAGILE)     # ★詰まっている → 壊れやすくする
        # ── ③★★★頭打ちなら大きくなる
        # ★★★大きくしてよいのは「本当に容量が足りない」時だけ。
        #   ・訓練も本番も止まっている → ★容量不足。★大きくする
        #   ・訓練だけ下がり続けている → ★丸暗記。★大きくすると**もっと暗記するだけ**
        #   ★足りていないのが容量でない時に容量を足すと、★太るだけで賢くならない。
        memorizing = gap > OVERFIT_GAP
        if memorizing and bad >= GROW_PATIENCE:
            print("  ★丸暗記している（差 %.3f）。★大きくしない。" % gap, flush=True)
        if (bad >= GROW_PATIENCE and vl > GROW_MIN_LOSS and not memorizing):
            # ★★★安い成長から先に試す。
            #   ① もう一周ぶん深くなる ── ★パラメータ0・保存サイズ変わらず。★安い
            #   ② 層を1枚足す         ── ★パラメータ増。★高い
            #   ③ 体を乗り換える       ── ★いちばん高い（引っ越し。別の回でやる）
            #   ★足りていないものが「深さ」なら①で足りる。★①で駄目なら②。
            cap = layer_cap(model.d)
            if len(model.blocks) < cap:
                # ★① 層を足す ── ★まだ細長くない範囲で
                n = model.grow()
                opt = torch.optim.AdamW(model.parameters(), lr=LR,
                                        weight_decay=0.01, betas=(0.9, 0.95))
                bad, grew = 0, grew + 1
                lr_now = LR                              # ★★大きくなった → 上げ直す
                print("  ★★★層が増えた → %d 層 / %.2f M（★振る舞いは変わっていない）"
                      % (n, model.n_params() / 1e6), flush=True)
            elif LOOP_OK and model.loops < MAX_LOOPS:
                # ★③ ループ ── ★★安いが弱い。★保存を小さくしたい時だけ
                r = model.loop_more()
                bad, grew = 0, grew + 1
                lr_now = LR
                print("  ★もう一周ぶん深くなった → %d 周（★パラメータは増えない。★ただし弱い）"
                      % r, flush=True)
            else:
                # ★② ★★これ以上は細長くなる。★「幅が欲しい」と自分で言う
                want_wider = True
                print("  ★★★これ以上、層を足すと細長くなる（%d 幅 / %d 層）。"
                      "★★次は**幅を広げたい**。" % (model.d, len(model.blocks)), flush=True)
                bad = 0

    model.eval()
    with torch.no_grad():
        val = torch.stack([model(*batch(va, model.ctx, BATCH))[1]
                           for _ in range(20)]).mean().item()

    # ── ★★★縮退していないか測る（★言い方の幅が細くなっていないか）
    #   ★蒸留を重ねると、★珍しい言い方から順に消えていく。★数字で見えるようにする。
    def spread(m):
        with torch.no_grad():
            xx, _ = batch(va, m.ctx, BATCH)
            lg, _ = m(xx)
            pr = F.softmax(lg, dim=-1)
            return float(-(pr * torch.log(pr + 1e-9)).sum(-1).mean())

    my_spread = spread(model)
    if teacher is not None:
        t_spread = spread(teacher)
        print("★言い方の幅: 先生 %.3f → わたし %.3f" % (t_spread, my_spread), flush=True)
        if my_spread < t_spread * 0.7:
            print("★★★細くなりすぎている。★次は先生の言うことを減らすべき。", flush=True)

    # ── ④★★★自己点検 ── 前より悪くなっていたら、前のわたしに戻す
    rolled = False
    if prev_val is not None and val > prev_val + WORSE_MARGIN and grew == 0:
        print("★★★前より悪くなった（%.4f → %.4f）。★この学習は採用しない。前のわたしに戻す。"
              % (prev_val, val), flush=True)
        model.load_state_dict(before)
        while len(model.blocks) > before_layers:
            model.blocks = model.blocks[:before_layers]
        val, rolled = prev_val, True

    torch.save({"model": model.state_dict(), "loops": model.loops,
                "kind": getattr(vocab, "kind", "char"), "arch": ARCH,
                "itos": getattr(vocab, "itos", None),
                "layers": len(model.blocks), "d": model.d, "h": model.h,
                "ctx": model.ctx, "val": val}, ckpt)

    # ★★★毎回、同じ書き出しで書かせる。★並べれば育ちが見える。
    #   ★出す前に必ず検閲する（★キーワードの網。★learn.py と同じもの）。
    prompts = ["わたしは", "第一条", "この法律において"]
    wrote = []
    for pr in prompts:
        try:
            txt = model.write(vocab, pr, 110, temp=0.75)
            txt = re.sub(r"\s+", " ", txt).strip()
            try:
                import learn as _L
                if not _L.safe(txt):
                    txt = "（出せない言葉が混じったので、これは出さない）"
            except Exception:
                pass
            wrote.append({"start": pr, "text": txt[:220]})
        except Exception:
            pass
    sample = wrote[0]["text"] if wrote else ""
    try:
        ptsize = os.path.getsize(ckpt)
    except Exception:
        ptsize = 0
    hist["runs"].append({
        "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "val": round(val, 4), "prev": round(prev_val, 4) if prev_val else None,
        "layers": len(model.blocks), "params": model.n_params(),
        "chars": len(text), "grew": grew, "rolledBack": rolled,
        "d": model.d, "loops": model.loops, "spread": round(my_spread, 4),
        "bytes": ptsize, "heads": model.h, "ctx": model.ctx, "vocab": len(vocab),
        "kind": getattr(vocab, "kind", "char"), "arch": ARCH,
        "wantWider": want_wider, "layerCap": layer_cap(model.d),
        "wrote": wrote,
        "movedBody": teacher is not None,
    })
    hist["runs"] = hist["runs"][-200:]
    hist["bestVal"] = round(min(r["val"] for r in hist["runs"]), 4)
    hist["layers"] = len(model.blocks)
    # ★★★次の回に「幅を広げたい」を伝える
    hist["wantWider"] = want_wider
    hist["nextD"] = (model.d * 2 if want_wider else model.d)
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
