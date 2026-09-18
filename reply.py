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
# ★★本数は多くてよい。★1本20トークン程度なので、★32本でも数秒
TRIES = int(os.environ.get("REALU_REPLY_TRIES", 32))
TEMP = float(os.environ.get("REALU_REPLY_TEMP", 0.9))
TOPP = float(os.environ.get("REALU_REPLY_TOPP", 0.9))    # ★裾を切る
# ★★ありふれ具合をどれだけ引くか。★0.6 → 1.0（2026-09-18）。
#   ★実測: ★「おなかすいた」に **「今日はありがとうございました。」** が勝っていた。
#     ★同じ回の候補に「★ですね。それでお昼ご飯食べましたか？」があったのに3位。
#   ★★下限（FLOOR）を入れてあるので、★引く量を増やしても
#     ★「珍しいだけの変な返事」は上がってこない。★だから強めにできる。
LAM = float(os.environ.get("REALU_REPLY_LAM", 1.0))
# ★★★短くて無難な返事が勝ちすぎるのを抑える（2026-09-18）。
#   ★点は1トークンあたりの平均なので長さで割ってはいるが、★それでも
#     ★★「そうなんですか。」のような**短い相槌**が有利なまま。
#   ★1文字あたり少しだけ足す。★★ただし上限つき（★長いほど良い、にはしない）。
LENB = float(os.environ.get("REALU_REPLY_LENB", 0.008))
LENB_MAX = int(os.environ.get("REALU_REPLY_LENB_MAX", 30))   # ★この字数ぶんで打ち止め
# ★★一番自然なものから、これ以上離れた候補は選ばない（★珍しさだけで勝たせない）
FLOOR = float(os.environ.get("REALU_REPLY_FLOOR", 0.70))
# ★★相手の言葉をこの割合まで拾うのは良い。★超えた分だけ減点（★オウム返し対策）
COPY_OK = float(os.environ.get("REALU_REPLY_COPY", 30.0))
# ★★下限で切りすぎないように、★最低この本数は必ず残す
KEEP_MIN = int(os.environ.get("REALU_REPLY_KEEP", 8))
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


def echo(t, k=4):
    """★★離れた所で同じ言い回しが出ていないか（★`loops` は隣り合う分しか見ない）。

    ★★★2026-09-17 に踏んだ: ★「暑かったら、暑かったですね」が **ループ率 0.0%** で
      1位に選ばれた。★「暑かった」が2回出ているのに、★隣り合っていないので
      ★`loops` では拾えなかった。
    ★★ありふれ具合を引く選び方は、★**珍しい言い方ほど有利**になる。
      ★だから「壊れているが珍しい」返事が勝ちやすい。★ここで落とす。
    ★返すのは「2回以上出てくる %d 文字のかたまり」が占める割合。
    """
    if len(t) < k * 2:
        return 0.0
    grams = [t[i:i + k] for i in range(len(t) - k + 1)]
    seen, dup = {}, 0
    for g in grams:
        seen[g] = seen.get(g, 0) + 1
    for g, c in seen.items():
        if c > 1:
            dup += c
    return 100.0 * dup / len(grams)


def copied(t, said, k=4):
    """★★★相手の言葉を、そのまま返していないか（★オウム返し）。

    ★★2026-09-17 に踏んだ: ★「今日は何してたの？」→ ★**「今日は何してたんですか？」**
      が1位になった。★質問に答える候補（「今日は、昼寝してました。」）は下に沈んだ。
    ★★★なぜ勝つか: ★オウム返しは**相手の言葉をほぼそのまま返す**ので、
      ★「その流れでの出やすさ」が飛び抜けて高くなる。
      ★しかも**ありふれてもいない**ので、★ありふれ具合を引く選び方でも損をしない。
      ★★**両方で得をする**。★だからここで別に見るしかない。
    ★少し拾うのは良い（★話題を受けている）。★**丸ごと**が駄目。
    ★返すのは「相手の発言にもある %d 文字のかたまり」が占める割合。
    """
    if len(t) < k or len(said) < k:
        return 0.0
    grams = [t[i:i + k] for i in range(len(t) - k + 1)]
    return 100.0 * sum(1 for g in grams if g in said) / len(grams)


def build_prompt(turns):
    """★往復を棚と同じ形に組む。★最後は必ずレアルの番で開いたままにする。"""
    lines = []
    for i, t in enumerate(turns):
        who = YOU if (len(turns) - i) % 2 == 1 else ME
        lines.append("%s「%s」" % (who, t.strip()))
    lines.append("%s「" % ME)
    return "\n".join(lines)


def _top_p(p, top_p):
    """★★裾を切る（nucleus）。★上位から足していって `top_p` に届いた所で打ち切る。

    ★★★素のサンプリングは、★6000語のうち**ほぼ0の裾**からも拾ってしまう。
      ★1回拾うと、そこから先がまるごと壊れる（★「ー」「�」が混ざるのはこれ）。
      ★確率の高い所だけ残せば、★同じ頭のまま出来が上がる。
    """
    import torch
    if not (0 < top_p < 1):
        return p
    s, idx = torch.sort(p, descending=True, dim=-1)
    c = torch.cumsum(s, dim=-1)
    keep = (c - s) < top_p              # ★★1個目は必ず残す
    s = s * keep
    s = s / s.sum(dim=-1, keepdim=True)
    out = torch.zeros_like(p)
    out.scatter_(-1, idx, s)
    return out


def score(model, vocab, prompt, reply):
    """★★`prompt` に続けて `reply` と言う、その言いやすさ（★1トークンあたり）。

    ★返ってくるのは対数確率の平均。★大きいほど「その流れで出やすい言葉」。
    """
    import torch
    import torch.nn.functional as F
    pi = vocab.encode(prompt) or [0]
    ri = vocab.encode(reply)
    if not ri:
        return -99.0
    ids = (pi + ri)[-model.ctx:]
    k = min(len(ri), len(ids) - 1)
    if k <= 0:
        return -99.0
    x = torch.tensor([ids], dtype=torch.long)
    with torch.no_grad():
        logits, _ = model(x[:, :-1])
        lp = F.log_softmax(logits[0, -k:].float(), dim=-1)
        tgt = x[0, -k:]
        return float(lp.gather(-1, tgt.unsqueeze(-1)).mean())


def gen(model, vocab, prompt, n, temp, top_p=0.9):
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
            p = _top_p(F.softmax(logits[:, -1] / temp, dim=-1), top_p)
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
    seen, cand = set(), []
    for i in range(TRIES):
        try:
            raw = G.no_src(gen(model, vocab, prompt, MAXTOK, TEMP, TOPP))
        except Exception as ex:
            print("  書けなかった:", type(ex).__name__, str(ex)[:80])
            continue
        t = cut(raw)
        if not t or t in seen or not safe(t):
            continue
        seen.add(t)
        cand.append(t)

    print("\n― %d本から選ぶ ―" % len(cand))
    if not cand:
        print("（まだ返せなかった）")
        return 0

    # ★★★選び方（★2026-09-16）。
    #   ★前は「繰り返しが少ないもの」だけで選んでいた。★それは壊れ方しか見ていない。
    #   ★★かといって「出やすいもの」で選ぶと、★★**必ず「そうですね」が勝つ** ──
    #     ★当たり障りのない返事は、どんな話の後でも出やすいから。
    #   ★★★なので **文脈での出やすさ − ありふれ具合** で選ぶ。
    #     ★「この話の後だから出てきた」度合いだけが残る（★MMI。Li+2016 と同じ考え）。
    #   ★`NEUTRAL` は「何の話も無い所で、その返事がどれだけ出やすいか」。
    NEUTRAL = "%s「" % ME
    rows = []
    for t in cand:
        s_ctx = score(model, vocab, prompt, t + "」")
        s_any = score(model, vocab, NEUTRAL, t + "」")
        lp = max(loops(t), echo(t))     # ★隣り合う繰り返し ＋ 離れた繰り返し
        cp = copied(t, turns[-1])       # ★★相手の言葉をそのまま返していないか
        pick = (s_ctx - LAM * s_any)
        pick -= 0.02 * lp                        # ★壊れているものは下げる
        pick -= 0.02 * max(0.0, cp - COPY_OK)    # ★★拾いすぎた分だけ下げる
        pick += LENB * min(len(t), LENB_MAX)     # ★★短い相槌が勝ちすぎるのを抑える
        rows.append((pick, s_ctx, s_any, lp, t, cp))

    # ★★★下限（★2026-09-17）。★**日本語として無理のあるものは、珍しくても選ばない。**
    #   ★ありふれ具合を引く選び方は、★**珍しい言い方ほど有利**になる。
    #   ★★実測: 「暑かったね、ダメだった！」が ★文脈 -1.69（かなり不自然）なのに
    #     ★ありふれ -2.54 の珍しさだけで4位まで上がってきていた。
    #   → ★一番自然なものから `FLOOR` 以上離れた候補は、★はじめから外す。
    #     ★★外した中から選ぶのではなく、★**残った中で「この話らしさ」を競わせる**。
    top_ctx = max(r[1] for r in rows)
    keep = [r for r in rows if r[1] >= top_ctx - FLOOR]
    # ★★★短い問いかけだと**全体の点が下がる**ので、★下限で切りすぎる（2026-09-18）。
    #   ★実測: ★「おなかすいた」で **32本中26本** を外していた。
    #   → ★何本かは必ず残す。★残った中で競わせる。
    if len(keep) < KEEP_MIN:
        keep = sorted(rows, key=lambda r: -r[1])[:KEEP_MIN]
    dropped = len(rows) - len(keep)
    rows = keep or rows
    rows.sort(key=lambda r: -r[0])
    for pick, sc, sa, lp, t, cp in rows[:8]:
        print("  %+.3f（文脈 %+.2f − ありふれ %+.2f / ループ%4.1f%% / まね%4.1f%%） %s"
              % (pick, sc, sa, lp, cp, t[:46]))
    if len(rows) > 8:
        print("  …ほか %d 本" % (len(rows) - 8))
    if dropped:
        print("  ★日本語として無理があるので外した: %d 本"
              "（文脈が %+.2f より下）" % (dropped, top_ctx - FLOOR))

    best = rows[0]
    # ★★前のやり方なら何を選んでいたかも出す（★直したことが効いているか毎回見えるように）
    old_loop = sorted(rows, key=lambda r: r[3])[0]
    old_plain = sorted(rows, key=lambda r: -r[1])[0]
    print("\n― 返事 ―")
    print("%s「%s」" % (ME, best[4]))
    if old_loop[4] != best[4]:
        print("   （ループ率だけで選んでいたら → 「%s」）" % old_loop[4][:46])
    if old_plain[4] != best[4]:
        print("   （出やすさだけで選んでいたら → 「%s」）" % old_plain[4][:46])

    # ★★★読める出口。★数字の良し悪しは人に読ませない
    generic = best[2] > best[1]          # ★文脈より「単体」のほうが出やすい＝当たり障りが無い
    print("\n― 判定 ―")
    print("  返事になっているか : %s" % ("○ 1番ぶんで閉じた" if best[4] else "× 空"))
    print("  繰り返し           : %s（%.1f%%）"
          % ("○ 少ない" if best[3] < 15 else "△ 多い" if best[3] < 40 else "× 壊れている", best[3]))
    print("  この話への返事か   : %s（文脈 %+.2f vs ありふれ %+.2f）"
          % ("× 当たり障りがない" if generic else "○ この流れで出てきた", best[1], best[2]))
    # ★★★ここは前は「拾ったほど良い」として出していた。★それが間違いだった ──
    #   ★拾いすぎ＝オウム返し。★2026-09-17 に「今日は何してたんですか？」で踏んだ。
    print("  相手の言葉のまね   : %s（%.0f%%）"
          % ("○ 適度" if best[5] <= COPY_OK else "× そのまま返している", best[5]))
    print("  使えた本数         : %d / %d" % (len(cand), TRIES))
    return 0


if __name__ == "__main__":
    sys.exit(main())
