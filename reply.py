# -*- coding: utf-8 -*-
"""★★★話しかけられたら、返事をする。

★★なぜ要るか（★2026-09-16）
  ★レアルは会話の形（`AA「…」` の往復）で学んでいるのに、★書かせ方が
    `speak.py` の「わたしは」から流し続ける形しか無かった。
  ★★だから出てくるのは**会話ではなく書き起こしの続き**で、
    ★相手の発言に**返している**ようには見えなかった。
  ★★★頭を変えずに、**入口の形を学んだ形に合わせるだけ**で返事になるはず ──
    ★それを確かめるための係。

★★形（★`fetch_talk.py` が作った棚と同じにする。★ここがずれると別物になる）
    AA「こんばんは」
    AB「こんばんは！」
    AA「今日は暑かったね」
    AB「            ← ★ここから先を書かせて、★`」` で止める

使い方:
  python reply.py "今日は暑かったね"
  python reply.py "こんばんは" "こんばんは！" "今日は暑かったね"   # ★往復を渡す（奇数個＝最後が相手）
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.environ.get("REALU_WORK", os.path.join(HERE, "work"))
ME, YOU = "AB", "AA"           # ★レアル / 相手（★棚の記号と同じ2文字）
TRIES = int(os.environ.get("REALU_REPLY_TRIES", 4))
TEMP = float(os.environ.get("REALU_REPLY_TEMP", 0.8))
MAXTOK = int(os.environ.get("REALU_REPLY_MAX", 60))


def loops(t):
    """★同じ並びの繰り返しが、どれだけを占めているか（★grow.py と同じ数え方）。"""
    if not t:
        return 100.0
    inloop = [False] * len(t)
    for k in range(1, 13):
        i = 0
        while i + 2 * k <= len(t):
            if t[i:i + k] == t[i + k:i + 2 * k]:
                j = i + k
                while t[j:j + k] == t[i:i + k]:
                    j += k
                for x in range(i, min(j + k, len(t))):
                    inloop[x] = True
                i = j
            else:
                i += 1
    return 100.0 * sum(inloop) / len(t)


def build_prompt(turns):
    """★往復を棚と同じ形に組む。★最後は必ずレアルの番で開いたままにする。"""
    lines = []
    for i, t in enumerate(turns):
        who = YOU if (len(turns) - i) % 2 == 1 else ME
        lines.append("%s「%s」" % (who, t.strip()))
    lines.append("%s「" % ME)
    return "\n".join(lines)


def gen(model, vocab, prompt, n, temp):
    """★★★入口のぶんを**トークンの数で**取り除いて、★書いた所だけを返す。

    ★★★文字で剥がしてはいけない（★2026-09-16 に踏んだ）。
      ★`model.write()` は「入口＋書いたもの」を**まとめて decode** して返すが、
      ★★**decode(encode(x)) は x に戻らない**（★BPE の正規化で字が変わる）。
      ★だから `text.startswith(prompt)` が False になり、★剥がし損ねて
        ★★**入口そのものを返事として出していた**。
      → ★新しく出たトークンだけを集めて、★**それだけを decode する**。
    ★ついでに `」` が出たらそこで止める（★60個ぶん無駄に書かない）。
    """
    import torch
    import torch.nn.functional as F
    ids = (vocab.encode(prompt) or [0])[-model.ctx:]
    idx = torch.tensor([ids], dtype=torch.long)
    use_cache = model.loops == 1
    caches = [[] for _ in model.blocks] if use_cache else None
    with torch.no_grad():
        if use_cache:
            logits, _ = model(idx, caches=caches, pos=0)
            pos = idx.shape[1]
        else:
            logits, _ = model(idx)
        new = []
        for _ in range(n):
            p = F.softmax(logits[:, -1] / temp, dim=-1)
            nxt = torch.multinomial(p, 1)
            new.append(int(nxt.item()))
            s = vocab.decode(new)
            if "」" in s or "\n" in s:     # ★1番ぶんが閉じた
                break
            if use_cache:
                if pos >= model.ctx:
                    caches = [[] for _ in model.blocks]
                    tail = torch.tensor([(ids + new)[-model.ctx:]], dtype=torch.long)
                    logits, _ = model(tail, caches=caches, pos=0)
                    pos = tail.shape[1]
                else:
                    logits, _ = model(nxt, caches=caches, pos=pos)
                    pos += 1
            else:
                tail = torch.tensor([(ids + new)[-model.ctx:]], dtype=torch.long)
                logits, _ = model(tail)
    return vocab.decode(new)


def cut(t):
    """★1番ぶんで切る。★`」` か改行が来たらそこまで。"""
    m = re.search(r"[」\n]", t)
    if m:
        t = t[:m.start()]
    return t.strip()


def main():
    turns = [a for a in sys.argv[1:] if a.strip()]
    if not turns:
        print("何を言われたのか書いてください。例: python reply.py \"今日は暑かったね\"")
        return 2
    ck = os.path.join(WORK, "realu.pt")
    if not os.path.exists(ck):
        print("★まだ頭がない。返事はできない。")
        return 1

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
    # ★★★これを忘れると、学習した時と違う表で書く（★2026-09-16 に踏んだ穴）
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

    prompt = build_prompt(turns)
    print("\n― 入口（★棚と同じ形）―")
    print(prompt + "…")

    # ★★何本か書かせて、★一番まともなものを出す。
    #   ★選び方: ①出せる言葉であること ②空でないこと ③繰り返しが少ないこと
    #   ★★★点は使わない（★loss は「返事になっているか」を何も見ていない）
    cand = []
    for i in range(TRIES):
        try:
            raw = G.no_src(gen(model, vocab, prompt, MAXTOK, TEMP))
        except Exception as ex:
            print("  書けなかった:", type(ex).__name__, str(ex)[:80])
            continue
        t = cut(raw)
        lp = loops(t)
        ok = bool(t) and safe(t)
        cand.append((lp, t, ok))
        print("  %d本目 ループ%5.1f%% %s %s"
              % (i + 1, lp, "○" if ok else "×", t[:56] or "（空）"))

    good = sorted([c for c in cand if c[2]], key=lambda c: c[0])
    print("\n― 返事 ―")
    if not good:
        print("（まだ返せなかった）")
        return 0
    print("%s「%s」" % (ME, good[0][1]))

    # ★★★読める出口。★数字の良し悪しは人に読ませない
    lp = good[0][0]
    hit = sum(1 for ch in set(turns[-1]) if len(ch.strip()) and ch in good[0][1])
    print("\n― 判定 ―")
    print("  返事になっているか : %s" % ("○ 1番ぶんで閉じた" if good[0][1] else "× 空"))
    print("  繰り返し           : %s（%.1f%%）"
          % ("○ 少ない" if lp < 15 else "△ 多い" if lp < 40 else "× 壊れている", lp))
    print("  相手の言葉を拾ったか: %s（%d 文字ぶん）"
          % ("○" if hit >= 2 else "△", hit))
    print("  使えた本数         : %d / %d" % (len(good), TRIES))
    return 0


if __name__ == "__main__":
    sys.exit(main())
