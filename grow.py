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
import hashlib
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

# ★★★GPUがあれば使う。★無ければCPU。★どちらでも同じコードが走る。
#   ★Actions は4CPU。★Kaggle は T4/P100 が週30時間ただで使える。
#   ★★頭が小さいのでGPUを埋めきれない。★だから batch を大きくして埋める。
def pick_device():
    try:
        if os.environ.get("REALU_CPU") != "1" and torch.cuda.is_available():
            return torch.device("cuda")
    except Exception:
        pass
    return torch.device("cpu")


DEV = pick_device()

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

# ★★★物差し ── **絶対に食べない文**を、ごはんの全部からすこしずつ取っておく。
#   ★これが無かった時の壊れ方（★2026-09-08 に見つけた）:
#     ・分け方が「うしろから2%」だった。★ごはんは laws→wiki→aozora→hanrei→kokkai→web の順。
#       → ★物差しが**webの尻尾だけ**になっていた。法令も本も国会も、一度も測っていない。
#     ・しかも web は毎日うしろに足される。★**毎回ちがう文で測っていた**。
#       → 「前より悪くなったから前のわたしに戻す」が、★別の問題の点数を比べていた。
#         ★これは育ちを黙って捨てる。★一番たちの悪い壊れ方。
#   ★★直し方: ①ごはんの種類に関係なく散らばるよう選ぶ ②一度決めたら**二度と変えない**
# ★★★物差しの行は**ずっと同じ**（★val.txt.gz は凍結）。★だから札も変えない。
#   ★点数はいつでも比べられる ＝ ★グラフが1本につながる。
#   ★★配合を変えた回の扱いは `mixTag` で別に見る（★「巻き戻し」の所）。
VAL_TAG = "fixed-holdout-v1"
val_tag = VAL_TAG          # ★★逃げ道に入ったら書き換える          # ★測り方が変わったら、ここを変える（★昔の点数と比べなくなる）
VAL_PER_MIL = int(os.environ.get("REALU_VAL_PERMIL", 3))   # ★千行に3行＝0.3%


# ★★★出典の印（<web タイトル> / <本 題名 / 著者>）は、★ごはんには要るが**書く時に出てはいけない**。
#   ★どこで知ったかを残すために本文へ埋めてある。★でもそれを真似して書くと意味不明になる。
#   ★（実測: 「なんぬの詐な子です。おお とよくすね。&lt;web 988年…」と出た）
SRC_MARK = re.compile("^<(web|本|会話) [^>]*>$")


# ★★★出典の印を、★書いたものから落とす。
#   ★ごはんには <web タイトル> / <本 題名 / 著者> が埋めてある（どこで知ったかを残すため）。
#   ★それを覚えて真似してしまう（実測: 「おお とよくすね。<web 988年（昭和21年）…」）。
#   → ★ごはんからは消さない（出典は残す）。★出す時だけ落とす。
SRC_OUT = re.compile("<(web|本|会話)[^>]*>?")


def no_src(t):
    return re.sub(r"[\s]+", " ", SRC_OUT.sub(" ", t)).strip()


def held_out(line):
    """★この行は物差しか。★★中身だけで決まる ── どこに置いてあっても同じ判定になる。"""
    if len(line) < 20:
        return False
    h = hashlib.sha1(line.encode("utf-8")).digest()
    return ((h[0] << 8) | h[1]) % 1000 < VAL_PER_MIL

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


def apply_rope(x, cos, sin, pos=0):
    """★pos は「この並びが全体の何番目から始まるか」。

    ★★覚えておく仕組み（KVキャッシュ）を使う時、★渡すのは新しい1個だけ。
    ★その1個は全体では pos 番目なので、★先頭から切ると**間違った回転**を当てる。
    """
    t = x.shape[-2]
    c = cos[pos:pos + t].unsqueeze(0).unsqueeze(0)
    s = sin[pos:pos + t].unsqueeze(0).unsqueeze(0)
    x1, x2 = x[..., 0::2], x[..., 1::2]
    return torch.stack((x1 * c - x2 * s, x1 * s + x2 * c), dim=-1).flatten(-2)


class Attn(nn.Module):
    def __init__(self, d, h):
        super().__init__()
        self.h, self.hd = h, d // h
        self.qkv = nn.Linear(d, 3 * d, bias=False)
        self.o = nn.Linear(d, d, bias=False)

    def forward(self, x, cos, sin, cache=None, pos=0):
        """★★★cache があれば、★前に計算した k,v を使い回す。

        ★cache は [k, v] の入れ物（★中身を書き換えて返す）。
        ★1文字書くたびに全部計算し直すのをやめる（★実測 8〜23倍）。
        """
        B, T, D = x.shape
        q, k, v = self.qkv(x).split(D, dim=2)
        q = q.view(B, T, self.h, self.hd).transpose(1, 2)
        k = k.view(B, T, self.h, self.hd).transpose(1, 2)
        v = v.view(B, T, self.h, self.hd).transpose(1, 2)
        q = apply_rope(q, cos, sin, pos)
        k = apply_rope(k, cos, sin, pos)
        if cache is not None:
            if cache:
                k = torch.cat([cache[0], k], dim=2)
                v = torch.cat([cache[1], v], dim=2)
            cache[:] = [k, v]
            # ★★新しい1個は、★過去すべてを見てよい（★先の方は存在しない）
            y = F.scaled_dot_product_attention(q, k, v, is_causal=(T > 1))
        else:
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

    def forward(self, x, cos, sin, cache=None, pos=0):
        x = x + self.attn(self.n1(x), cos, sin, cache, pos)
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
        w = torch.empty(n_old + n_new, d, device=old.device, dtype=old.dtype)
        nn.init.normal_(w, std=0.02)
        w[:n_old] = old
        # ★★新しい入れ物は、★元と同じ場所（GPUならGPU）に作る
        self.tok = nn.Embedding(n_old + n_new, d).to(old.device)
        self.tok.weight.data = w
        self.head = nn.Linear(d, n_old + n_new, bias=False).to(old.device)
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

    def forward(self, idx, targets=None, caches=None, pos=0):
        x = self.tok(idx)
        for r in range(self.loops):
            x = x + self.loop_emb.weight[r]     # ★何周目かを教える
            for i, blk in enumerate(self.blocks):
                c = caches[i] if caches is not None else None
                x = blk(x, self.rc, self.rs, c, pos)
        logits = self.head(self.nf(x))
        if targets is None:
            return logits, None
        return logits, F.cross_entropy(logits.view(-1, logits.size(-1)), targets.reshape(-1))

    @torch.no_grad()
    def write(self, vocab, start="", n=200, temp=0.8):
        # ★★頭がGPUにいる時、入り口もGPUに置く（★でないと必ず落ちる）
        dev = next(self.parameters()).device
        idx = torch.tensor([vocab.encode(start) or [0]], dtype=torch.long, device=dev)
        # ★★★覚えておく（KVキャッシュ）。
        #   ★前は1文字書くたびに 256文字ぶん全部を計算し直していた。
        #   ★実測: 2.9M で 8倍 / 16M で 13倍 / 90M で 23倍（★大きいほど効く）。
        #   ★★ループを使う時は同じ層を何度も通るので、★その時は今まで通り。
        use_cache = self.loops == 1
        caches = [[] for _ in self.blocks] if use_cache else None
        out = idx
        if use_cache:
            logits, _ = self(idx, caches=caches, pos=0)
            pos = idx.shape[1]
        else:
            logits, _ = self(idx[:, -self.ctx:])
        for _ in range(n):
            p = F.softmax(logits[:, -1] / temp, dim=-1)
            nxt = torch.multinomial(p, 1)
            out = torch.cat([out, nxt], dim=1)
            if use_cache:
                if pos >= self.ctx:                 # ★★窓からはみ出したら、★覚え直す
                    caches = [[] for _ in self.blocks]
                    tail = out[:, -self.ctx:]
                    logits, _ = self(tail, caches=caches, pos=0)
                    pos = tail.shape[1]
                else:
                    logits, _ = self(nxt, caches=caches, pos=pos)
                    pos += 1
            else:
                logits, _ = self(out[:, -self.ctx:])
        return vocab.decode(out[0].tolist())


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


class Pantry:
    """★★★棚。★ごはんをトークンのまま置き、★必要な所だけディスクから読む。

    ★前は毎回ぜんぶメモリに載せていた（実測: 下ごしらえ12.8分 / メモリ8.8GB）。
    ★★棚なら **メモリ増 0.0 MB / 720万個/秒**（試作で実測）。
    """

    def __init__(self, d):
        import numpy as np
        self.np = np
        self.parts, starts, tot = [], [], 0
        for nm in sorted(os.listdir(d)):
            if not nm.endswith(".bin"):
                continue
            a = np.memmap(os.path.join(d, nm), dtype=np.uint16, mode="r")
            if len(a) == 0:
                continue
            self.parts.append(a)
            starts.append(tot)
            tot += len(a)
        self.starts = np.array(starts) if starts else np.array([0])
        self.n = tot
        # ★★棚はトークンなので、★ここから「文字数」は数えられない。
        #   ★棚を作った時に数えた数を meta.json から持ち歩く。
        #   ★古い棚には入っていない（★次に棚を作り直した時から入る）。
        self.chars = 0
        self.mix = None          # ★★どの配合で作られた棚か
        try:
            with open(os.path.join(d, "meta.json"), encoding="utf-8") as f:
                m = json.load(f) or {}
            self.chars = int(m.get("chars") or 0)
            self.mix = m.get("mix")
        except Exception:
            pass

    def __len__(self):
        return self.n

    def window(self, i, ctx):
        """★i から ctx 個。★棚をまたいだら継ぎ足す。"""
        np = self.np
        out, need = [], ctx
        k = int(np.searchsorted(self.starts, i, "right")) - 1
        off = i - int(self.starts[k])
        while need > 0 and k < len(self.parts):
            a = self.parts[k]
            take = min(need, len(a) - off)
            if take > 0:
                out.append(np.asarray(a[off:off + take]))
                need -= take
            k += 1
            off = 0
        if not out:
            return np.zeros(ctx, dtype=np.uint16)
        w = out[0] if len(out) == 1 else np.concatenate(out)
        if len(w) < ctx:
            w = np.pad(w, (0, ctx - len(w)))
        return w


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
    # ★★ごはんは int32 で持つ（★long の半分）。★使う所だけ long にする
    if isinstance(data, Pantry):
        import numpy as np
        xs = np.stack([data.window(int(i), ctx + 1) for i in ix]).astype(np.int64)
        t = torch.from_numpy(xs)
        x, y = t[:, :ctx], t[:, 1:ctx + 1]
    else:
        x = torch.stack([data[i:i + ctx] for i in ix]).long()
        y = torch.stack([data[i + 1:i + ctx + 1] for i in ix]).long()
    if DEV.type != "cpu":
        x = x.to(DEV, non_blocking=True)
        y = y.to(DEV, non_blocking=True)
    return x, y


def _drop_untagged(h):
    """★★★物差しの分からない記録は捨てる。

    ★2026-09-09: `runs[0]` に **手で入れた偽の loss 2.1454** が残っていた
      （★`valTag` なし・`stoppedAt` なし・`arch` は gpt2＝いまと別物）。
    ★★これが `bestVal = min(val)` に効いて**永久に最高記録**になり、
      ★サイトのグラフの1点目にもなって「★悪くなった」ように見せていた。
    ★★**物差しが書いていない点数は、どの点数とも比べられない。** だから残さない。
    """
    runs = h.get("runs") or []
    keep = [r for r in runs if r.get("valTag")]
    if len(keep) != len(runs):
        print("★物差しの分からない記録を %d 件そっと外した" % (len(runs) - len(keep)),
              flush=True)
    h["runs"] = keep
    return h


def load_hist():
    try:
        with open(HIST, encoding="utf-8") as f:
            return _drop_untagged(json.load(f))
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
    if DEV.type == "cuda":
        print("★★GPU で学ぶ: %s" % torch.cuda.get_device_name(0), flush=True)
    else:
        print("★CPU で学ぶ（%d本）" % THREADS, flush=True)
    os.makedirs(WORK, exist_ok=True)
    hist = load_hist()
    # ★★★ここから時計を回す。
    #   ★前は「学習の直前」から測っていたが、★予算は「ジョブの残り」で計算している。
    #     → ★下ごしらえ（ごはんを開く・重複削り・encode）が**予算の外**にいた。
    #   ★そこが伸びると、★予算を守ったつもりで時間切れになる。
    t_start = time.time()

    # ★★★どこまで進んだかを、★外から見える形で刻む。
    #   ★Actions のログは認証が要る。★私（外から見る側）には読めない。
    #   → ★★足跡を残して、転んだ時にリポジトリへ書き出す。
    def step_log(what):
        try:
            import resource
            mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
        except Exception:
            try:
                import psutil
                mb = psutil.Process().memory_info().rss / 1024 / 1024
            except Exception:
                mb = -1
        line = "[%5.1f分 / メモリ %6.0f MB] %s" % ((time.time() - t_start) / 60, mb, what)
        print(line, flush=True)
        try:
            with open(os.path.join(WORK, "trace.txt"), "a", encoding="utf-8") as f:
                f.write(line + chr(10))
        except Exception:
            pass

    try:
        os.remove(os.path.join(WORK, "trace.txt"))
    except Exception:
        pass
    step_log("はじめ")

    # ★★★棚（pantry）があれば、★下ごしらえを丸ごと飛ばす。
    #   ★前は毎回「開く → 重複を削る → トークンに変換 → 全部メモリに載せる」。
    #     ★実測（run#20）: ★12.8分 / メモリ最大 8,826 MB。
    #   ★1回60分で学ぶ形にすると、★そのうち13分（21%）が下ごしらえになる。
    #   ★棚が無ければ今まで通り（★片方だけ壊れても止まらない）。
    pantry = None
    pdir = os.path.join(WORK, "pantry")
    if os.path.isdir(pdir) and any(f.endswith(".bin") for f in os.listdir(pdir)):
        try:
            pantry = Pantry(pdir)
            print("★★棚から食べる: %s 個（★開かない・メモリに載せない）"
                  % format(len(pantry), ","), flush=True)
        except Exception as e:
            print("★棚が読めなかった（%s）。★今まで通りにする。"
                  % type(e).__name__, flush=True)
            pantry = None
    val_tag = VAL_TAG      # ★逃げ道に入ったら書き換える（★別の物差しと比べないため）
    # ★★★いまのごはんの配合を短い札にする。★前の回と違えば「配合が変わった回」。
    mix_tag = json.dumps(getattr(pantry, "mix", None) or {}, sort_keys=True,
                         ensure_ascii=False)[:200]
    mix_changed = False

    # ── ①★ごはんを読む（★法令＋判例＋**webで自分が読んだもの**）
    if pantry is None:
        texts = []
        sizes = {}
        # ★★★動かないもの（法令・Wikipedia）を先に、★増えるもの（判例・会議録・読んだもの）を後に。
        #   ★そうすると「新しく足された分」がいつも後ろに来るので、★短期の山が作れる。
        for name in ("laws.txt", "wiki.txt", "aozora.txt", "talk.txt",
                     "hanrei.txt", "kokkai.txt", "web.txt"):
            for p in (os.path.join(WORK, name + ".gz"), os.path.join(WORK, name)):
                if not os.path.exists(p):
                    continue
                # ★★圧縮して持つ（★日本語は1/3になる。★置き場所が3倍長持ちする）
                # ★途中で切れた字があっても止まらない（★ごはんが欠けても生きる）
                op = gzip.open if p.endswith(".gz") else open
                # ★★★1つ壊れていても、★残りは食べる（★全部を道連れにしない）
                try:
                    with op(p, "rt", encoding="utf-8", errors="ignore") as f:
                        texts.append(f.read())
                except Exception as e:
                    print("  ★★★%s が壊れている（%s）。★捨てて次へ。"
                          % (name, type(e).__name__), flush=True)
                    os.remove(p)
                    continue
                sizes[name] = len(texts[-1])   # ★長さだけ。★前は全文を持っていた
                # ★★★同じ名前の非圧縮版が隣にあると、それは**読まれない**。
                #   ★2026-09-08: read_web.py が web.txt に書き、包みが web.txt.gz に足され、
                #     ★.gz を先に見つけて打ち切るので **1日4万ページが丸ごと消えていた**。
                #   ★★黙って消えるのが一番悪い。★見つけたら大声で言う。
                other = os.path.join(WORK, name)
                if p.endswith(".gz") and os.path.exists(other):
                    print("  ★★★%s が隣にある。★これは読まれていない（%.1f MB）"
                          % (name, os.path.getsize(other) / 1024 / 1024), flush=True)
                print("  ごはん %s: %.1f MB" % (os.path.basename(p),
                                                os.path.getsize(p) / 1024 / 1024), flush=True)
                break
        if not texts:
            print("★ごはんが無い。work/ に laws.txt を置いて。")
            return 1
        # ★★★全部を1本に繋ぐ前に、★読み終わった写しを手放す。
        #   ★前は texts（各ファイルの全文）を持ったまま繋いだ写しも作っていた。
        #   ★日本語800M字なら、それだけで数GB。★16GBの機械では効いてくる。
        text = (chr(10)).join(texts)
        texts.clear()
        del texts
        step_log("ごはんを開いた")
        before = len(text)

        # ── ①★★★同じ行を何度も食べない。
        #   ★法令の 18.3% は重複行（実測）。「その他参考となるべき事項」が 1,329 回など。
        #   ★★小さい頭は、言葉を学ぶ前にこの定型文を**丸暗記する**。
        #     ★それが一番点の上がる近道だから。★★近道を塞ぐ。
        seen = {}
        kept = []
        held = []                      # ★★物差し。★ここに入った文は一度も食べない
        for ln in text.split("\n"):
            key = ln.strip()
            if len(key) < 10:
                kept.append(ln)
                continue
            if SRC_MARK.match(key):
                kept.append(ln)          # ★ごはんには残す（★区切りとして要る）
                continue                 # ★でも物差しには入れない
            if held_out(key):
                held.append(key)          # ★食べずに、測るためだけに取っておく
                continue
            n = seen.get(key, 0)
            if n < DUP_MAX:
                seen[key] = n + 1
                kept.append(ln)
        text = "\n".join(kept)
        del kept, seen                  # ★★ごはんの写しを2つ抱えない
        step_log("重複を削った")
    else:
        # ★★★棚があるので、開かない・削らない。
        text = ""
        held = []
        step_log("棚をひらいた")
    if pantry is None:
        print("★コーパス %.1f 万字（★同じ行を削って %.1f%% 減）"
              % (len(text) / 10000, (1 - len(text) / max(1, before)) * 100),
              flush=True)

    # ── ②★前のわたしを起こす
    # ★★★ことばの単位を用意する
    tokf = os.path.join(WORK, "tok.json")
    ckpt = os.path.join(WORK, "realu.pt")
    st = None
    if os.path.exists(ckpt):
        # ★★★途中で切れた .pt は、★捨てて生まれ直す（★死に続けるよりまし）
        try:
            st = torch.load(ckpt, map_location="cpu", weights_only=False)
        except Exception as e:
            print("★★★前のわたしが壊れている（%s）。★はじめから目を開ける。"
                  % type(e).__name__, flush=True)
            os.remove(ckpt)
            st = None
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
        model = model.to(DEV)
        prev_val = st.get("val")
        # ★★★ごはんの配合を変えた回は、★**巻き戻さない**。
        #   ★巻き戻しても配合は戻らないので、★永久に巻き戻し続けて学習が止まる。
        #   ★点数は前と比べられる（★物差しは同じ）ので、★記録には残して見せる。
        if st.get("mixTag") != mix_tag:
            mix_changed = True
            print("★★ごはんの配合が変わった。★この回は前より悪くても巻き戻さない",
                  flush=True)
        # ★★★測り方が変わったなら、前の点数は**別の問題の点数**。比べてはいけない。
        if st.get("valTag") != val_tag:
            prev_val = None
            print("★物差しが変わった。★前の点数とは比べない（★比べると嘘になる）", flush=True)
        print("★前のわたし: %d 層 / %.2f M / これまでの loss %.4f"
              % (len(model.blocks), model.n_params() / 1e6, prev_val or -1), flush=True)
    else:
        vocab = BpeVocab(tokf) if os.path.exists(tokf) else CharVocab(text=text)
        model = Realu(len(vocab), loops=LOOPS0)
        model = model.to(DEV)
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
        model = model.to(DEV)
        prev_val = None                       # ★別の体なので、前の点数とは比べない
        print("★★★新しい体に移る: 幅 %d → %d / %.2f M → %.2f M / 先生は前のわたし"
              % (teacher.d, model.d, teacher.n_params() / 1e6,
                 model.n_params() / 1e6), flush=True)

    # ── ★★★はじめて見る文字を覚える（★語彙も育つ）
    new_chars = (sorted((set(text) | set(chr(10).join(held))) - set(vocab.itos))
                 if getattr(vocab, "kind", "char") == "char" else [])
    if new_chars:
        vocab.itos = list(vocab.itos) + new_chars
        vocab.stoi = {c: i for i, c in enumerate(vocab.itos)}
        model.learn_chars(len(new_chars))
        print("★はじめて見た字を %d 個おぼえた（語彙 %d）：%s"
              % (len(new_chars), len(vocab), "".join(new_chars[:20])), flush=True)

    # ★★★物差しは**一度作ったら変えない**。
    #   ★毎回ちがう文で測ると、「前より良くなったか」が意味を失う。
    #   ★★キャッシュが消えても復活できるよう、これも鍵つきでしまう（grow.yml 側）。
    valf = os.path.join(WORK, "val.txt.gz")
    val_text = None
    if os.path.exists(valf):
        # ★★★途中で切れた .gz は、★捨てて作り直す。
        #   ★前は毎回ここで死んで、★人が消しに来るまで直らなかった。
        try:
            with gzip.open(valf, "rt", encoding="utf-8", errors="ignore") as f:
                val_text = f.read()
        except Exception as e:
            print("★★★物差しが壊れている（%s）。★作り直す。" % type(e).__name__, flush=True)
            os.remove(valf)
            val_text = None
    if val_text is not None:
        print("★物差しは前と同じもの（%.1f 万字）。★だから前の点数と比べられる"
              % (len(val_text) / 10000), flush=True)
    else:
        val_text = (chr(10)).join(held)
        # ★★★途中で切れた .gz は、★以後**毎回**ここで落ちる（★人が消すまで直らない）。
        #   → ★別名で書いてから、★最後に名前を付け替える。
        with gzip.open(valf + ".tmp", "wt", encoding="utf-8", newline=chr(10)) as f:
            f.write(val_text)
        os.replace(valf + ".tmp", valf)
        print("★物差しを作った（%.1f 万字 / %d 行）。★★これはもう変えない"
              % (len(val_text) / 10000, len(held)), flush=True)

    # ★★★10億字を一度に encode すると**メモリで死ぬ**。
    #   ★Python の list は1個あたり8バイトの指し先＋28バイトの整数。
    #     6億個なら 5GB + 16GB。★16GBの機械では入らない。
    #   ★★分けて encode して、★int32 でつなぐ（★long の半分で済む）。
    #   ★make_tok.py は同じ理由で既に直した。★こちらが残っていた。
    def encode_big(t):
        # ★★★numpy が無い機械でも動く（★run#13 はこれで落ちた）。
        #   ★道具ひとつ足りないだけで全部止まるのは、★仕組みの方が悪い。
        step = 4_000_000
        out = []
        for i in range(0, len(t), step):
            out.append(torch.tensor(vocab.encode(t[i:i + step]), dtype=torch.int32))
        if not out:
            return torch.zeros(0, dtype=torch.int32)
        return torch.cat(out)

    # ★★★棚があれば、★変換しない（もうトークンになっている）
    ids = pantry if pantry is not None else encode_big(text)
    step_log("トークンにした")
    va = encode_big(val_text)

    # ★★★ソース別の物差し（★診断用。★全体の点数は今までどおり動かさない）
    #   ★★なぜ要るか: ★全体の1つの数字だと、★「国会が少し落ちて会話が大きく上がった」
    #     ★のような**中身の入れ替わり**が完全に潰れる。
    #   ★物差しの行は凍結したまま。★どこからどこまでがどのソースかの表だけを使う。
    va_src = {}
    try:
        vm = os.path.join(WORK, "pantry", "val_marks.json")
        with open(vm, encoding="utf-8") as f:
            vmarks = json.load(f) or {}
        vlines = val_text.split(chr(10))
        # ★★対応表は「物差しの中の位置の一覧」。★物差しの行そのものは触っていない
        if isinstance(vmarks, dict) and vmarks.get("format") == "indices":
            if vmarks.get("total") == len(vlines):
                for name, idxs in (vmarks.get("src") or {}).items():
                    seg = chr(10).join(vlines[i] for i in idxs if 0 <= i < len(vlines))
                    if len(seg) >= 2000:        # ★短すぎるソースは測らない（★雑音になる）
                        va_src[name.replace(".txt", "")] = encode_big(seg)
                print("★ソース別の物差し（トークン）: %s ／ 照合できなかった行 %s" % (
                    " / ".join("%s %.1f万" % (k, len(v) / 10000) for k, v in va_src.items()),
                    vmarks.get("unmatched")), flush=True)
            else:
                print("★★ソース別の対応表が物差しと合わない（%s ≠ %d）。★使わない"
                      % (vmarks.get("total"), len(vlines)), flush=True)
        elif vmarks:
            print("★ソース別の対応表が古い形式。★使わない", flush=True)
    except FileNotFoundError:
        pass
    except Exception as e:
        print("★ソース別の物差しは用意できなかった（%s）" % type(e).__name__, flush=True)

    tr = ids
    # ★物差しが短すぎると測れない。★その時だけ昔のやり方に落とす（★正直に言う）
    if len(va) < model.ctx * 8:
        cut = int(len(ids) * 0.98)
        tr, va = ids[:cut], ids[cut:]
        print("★★物差しが足りないので、うしろから2%%で測る（★前の点数とは比べない）", flush=True)
        prev_val = None
        val_tag = "tail2-fallback"   # ★★★別の物差し。印も変える

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

    step_log("学びはじめ")
    opt = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=0.01, betas=(0.9, 0.95))
    # ★★★「良くなったか」を、★回をまたいで数える。
    #   ★前は毎回 best=9e9 から始めていた。すると:
    #     ・★新しい回の1回目は**必ず「良くなった」判定**になる（実際は悪化していても）
    #     ・★bad が毎回0に戻るので、★**5回連続で止まる**にほぼ到達しない
    #     → ★★大きくなる判定が、事実上**一度も動けなかった**
    #   ★体が変わった回（幅を倍にした直後）は比べられないので、★そこはリセットする。
    best = prev_val if prev_val is not None else 9e9
    bad = int(hist.get("bad") or 0) if prev_val is not None else 0
    grew = 0
    if bad:
        print("★前の回から「良くならない」が %d 回続いている（%d で大きくなる）"
              % (bad, GROW_PATIENCE), flush=True)
    want_wider = False          # ★★★「幅が欲しい」と自分で言うための印
    lr_now = LR

    # ★★★Adam の慣性（勢い）を、前の回から引き継ぐ。
    #   ★これは数百歩かけて溜まったもの。★捨てると冷えた状態に戻り、
    #   ★loss が跳ねて ★50〜200歩ぶんの収束が無駄になる（研究の実測）。
    #   ★★前は毎回まっさらから作り直していた。★回が短いほど損が大きかった。
    #   ★体が変わった回（幅を倍・層が増えた）は形が違うので引き継がない。
    if st and st.get("opt") and teacher is None and prev_val is not None:
        try:
            opt.load_state_dict(st["opt"])
            sch = st.get("sched") or {}
            lr_now = float(sch.get("lr_now") or LR)
            print("★前の回の勢いを引き継いだ（lr %.1e）" % lr_now, flush=True)
        except Exception as e:
            print("★勢いは引き継げなかった（%s）。★冷えた状態から始める。"
                  % type(e).__name__, flush=True)
    t0 = t_start          # ★★下ごしらえも予算の内側

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
    # ★★★時間の予算。★これを超えたら**途中でも切り上げて、頭を残す**。
    #   ★2026-09-08: 4,000歩に182分かかる見込みなのに残りが145分しかなく、
    #     ★時間切れで**頭が1つも残らない**ところだった。
    #   ★★歩数を当てにいくのではなく、★「必ず残す」を保証する。
    budget = float(os.environ.get("REALU_TIME_BUDGET", 150)) * 60
    stopped_early = 0
    for step in range(1, STEPS + 1):
        if time.time() - t0 > budget:
            stopped_early = step
            print("★★時間の予算を使い切った（%d/%d 歩）。★ここまでを残す。"
                  % (step, STEPS), flush=True)
            break
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

    # ★★★ここから「残す」までの間で転んだら、★学習が丸ごと消える。
    #   ★測るのに失敗しても、★頭だけは必ず残す（★下の torch.save まで必ず行く）。
    def spread(m):
        """★言い方の幅。★蒸留を重ねると珍しい言い方から消えるので、数字で見る。"""
        with torch.no_grad():
            xx, _ = batch(va, m.ctx, BATCH)
            lg, _ = m(xx)
            pr = F.softmax(lg, dim=-1)
            return float(-(pr * torch.log(pr + 1e-9)).sum(-1).mean())

    model.eval()
    val = None
    my_spread = 0.0
    rolled = False
    by_src = {}                 # ★★ソース別の点数（★診断用）
    try:
        with torch.no_grad():
            val = torch.stack([model(*batch(va, model.ctx, BATCH))[1]
                               for _ in range(20)]).mean().item()
        my_spread = spread(model)
        # ★★★ソース別にも測る（★全体の点数の決め方は変えない）
        for _nm, _vv in va_src.items():
            if len(_vv) < model.ctx * 4:
                continue
            try:
                with torch.no_grad():
                    by_src[_nm] = round(torch.stack(
                        [model(*batch(_vv, model.ctx, BATCH))[1]
                         for _ in range(6)]).mean().item(), 4)
            except Exception:
                pass
        if by_src:
            print("★ソース別: %s" % " / ".join(
                "%s %.4f" % (k, v) for k, v in sorted(by_src.items(),
                                                      key=lambda x: x[1])), flush=True)
        if teacher is not None:
            t_spread = spread(teacher)
            print("★言い方の幅: 先生 %.3f → わたし %.3f" % (t_spread, my_spread), flush=True)
            if my_spread < t_spread * 0.7:
                print("★★★細くなりすぎている。★次は先生の言うことを減らすべき。", flush=True)

        # ── ④★★★自己点検 ── 前より悪くなっていたら、前のわたしに戻す
        if (prev_val is not None and not mix_changed
                and val > prev_val + WORSE_MARGIN and grew == 0):
            print("★★★前より悪くなった（%.4f → %.4f）。★この学習は採用しない。前のわたしに戻す。"
                  % (prev_val, val), flush=True)
            model.load_state_dict(before)
            while len(model.blocks) > before_layers:
                model.blocks = model.blocks[:before_layers]
            val, rolled = prev_val, True
    except Exception as e:
        print("★★★測れなかった（%s）。★それでも頭は残す。" % type(e).__name__, flush=True)
        if val is None:
            val = prev_val if prev_val is not None else float("nan")

    # ★★保存はCPUに戻してから。★GPUのまま保存すると、CPUの回が読めない
    # ★★★保存は**CPUに戻してから、別名で書いて、名前を付け替える**。
    #   ★GPUのまま保存すると、CPUの回が読めない。
    #   ★1つずつ .cpu() すると、★出口と入り口で共有している表が**2つに分かれて太る**
    #     （★実測: 語彙6000/幅192 で +4.6MB ＝ +47%）。★丸ごと移せば共有が保たれる。
    #   ★途中で切れた .pt は、★以後ずっと読めない。
    _was = next(model.parameters()).device
    model.to("cpu")
    torch.save({"model": model.state_dict(), "loops": model.loops,
                "kind": getattr(vocab, "kind", "char"), "arch": ARCH,
                "itos": getattr(vocab, "itos", None),
                "layers": len(model.blocks), "d": model.d, "h": model.h,
                                "ctx": model.ctx, "val": val, "valTag": val_tag,
                "mixTag": mix_tag,
                # ★★慣性も一緒に残す（★重みの2倍の大きさになるが、それに見合う）
                "opt": opt.state_dict(),
                "sched": {"lr_now": lr_now, "best": best, "bad": bad}},
               ckpt + ".tmp")
    os.replace(ckpt + ".tmp", ckpt)
    model.to(_was)

    # ★★★毎回、同じ書き出しで書かせる。★並べれば育ちが見える。
    #   ★出す前に必ず検閲する（★キーワードの網。★learn.py と同じもの）。
    prompts = ["わたしは", "第一条", "この法律において"]
    wrote = []
    for pr in prompts:
        try:
            txt = no_src(model.write(vocab, pr, 110, temp=0.75))
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
    # ★★★巻き戻した回の判断で脱皮しない。
    #   ★「前より悪くなったので採用しない」と決めた回が、★同時に「幅が欲しい」と
    #   言い残すと、★**失敗した回の判断で体を作り直す**ことになる。
    #   ★★体を変えるのは、★ちゃんと学べた回が「もう頭打ち」と言った時だけ。
    if rolled:
        want_wider = False

    hist["runs"].append({
        "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "val": round(val, 4), "prev": round(prev_val, 4) if prev_val else None, "valTag": VAL_TAG, "stoppedAt": stopped_early,
        "layers": len(model.blocks), "params": model.n_params(),
        # ★★棚から食べる時は `text` が空なので、★len(text) だと 0 になる。
        "chars": (pantry.chars if pantry is not None else len(text)),
        "tokens": len(ids),          # ★★実際に食べている単位はこちら
        "grew": grew, "rolledBack": rolled,
        "d": model.d, "loops": model.loops, "spread": round(my_spread, 4),
        "bytes": ptsize, "heads": model.h, "ctx": model.ctx, "vocab": len(vocab),
        "kind": getattr(vocab, "kind", "char"), "arch": ARCH,
        "wantWider": want_wider, "layerCap": layer_cap(model.d),
        "mixChanged": mix_changed,
        "bySrc": by_src,        # ★★ソース別の点数（★全体の点数とは別の、中身の内訳）
        "wrote": wrote,
        "movedBody": teacher is not None,
    })
    hist["runs"] = hist["runs"][-200:]
    hist["bestVal"] = round(min(r["val"] for r in hist["runs"]), 4)
    # ★★次の回に引き継ぐ（★体が変わったら0から）
    hist["bad"] = 0 if (grew or rolled) else bad
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
