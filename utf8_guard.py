# -*- coding: utf-8 -*-
"""★★★字が壊れない書き方（★2026-11-04）。

★語の切り方はバイト単位（ByteLevel BPE）なので、★単位の約16%は**字の途中**で切れている。
★素のまま引くと、★字の途中の単位を拾ったり、★字の途中で書き終えたりして「�」が出た
  （★said.json の60回のうち39回に「�」）。
→ ★UTF-8 の続きの決まり（★次に来てよいバイトの範囲）を表にして、
  ★★**字が壊れる単位は選ばない**。★最後に半端が残ったら落とす。
"""
import torch


def _byte_of_char():
    # ★ByteLevel の「字 → バイト」（★GPT-2 の bytes_to_unicode の逆）
    bs = list(range(33, 127)) + list(range(161, 173)) + list(range(174, 256))
    cs = bs[:]
    n = 0
    for b in range(256):
        if b not in bs:
            bs.append(b)
            cs.append(256 + n)
            n += 1
    return {chr(c): b for b, c in zip(bs, cs)}


def token_bytes(tok):
    """★各単位のバイト列。★ByteLevel でない語の切り方なら None。"""
    u = _byte_of_char()
    out = []
    for i in range(tok.get_vocab_size()):
        s = tok.id_to_token(i) or ""
        if any(ch not in u for ch in s):
            return None
        out.append(bytes(u[ch] for ch in s))
    return out


S0 = (0, 0, 0)  # ★状態 = (あと何バイト, 次のバイトの下限, 上限)。★S0 が字の切れ目


def _step(st, x):
    need, lo, hi = st
    if need:
        if not (lo <= x <= hi):
            return None
        need -= 1
        return (need, 0x80, 0xBF) if need else S0
    if x < 0x80:
        return S0
    if 0xC2 <= x <= 0xDF:
        return (1, 0x80, 0xBF)
    if x == 0xE0:
        return (2, 0xA0, 0xBF)          # ★ここを 0x80 からにすると「�」が残る
    if 0xE1 <= x <= 0xEC or 0xEE <= x <= 0xEF:
        return (2, 0x80, 0xBF)
    if x == 0xED:
        return (2, 0x80, 0x9F)
    if x == 0xF0:
        return (3, 0x90, 0xBF)
    if 0xF1 <= x <= 0xF3:
        return (3, 0x80, 0xBF)
    if x == 0xF4:
        return (3, 0x80, 0x8F)
    return None


def _walk(st, bs):
    for x in bs:
        st = _step(st, x)
        if st is None:
            return None
    return st


def table(tb):
    """★OK[s]: 状態 s で選んでよい単位（bool）。★NXT[s][i]: 次の状態の番号（-1 は不可）。"""
    states, idx, nxt = [S0], {S0: 0}, []
    k = 0
    while k < len(states):
        row = []
        for b in tb:
            n = _walk(states[k], b)
            if n is not None and n not in idx:
                idx[n] = len(states)
                states.append(n)
            row.append(-1 if n is None else idx[n])
        nxt.append(row)
        k += 1
    ok = [torch.tensor([j >= 0 for j in row]) for row in nxt]
    return ok, nxt
