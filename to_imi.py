# -*- coding: utf-8 -*-
"""★★★「言葉→意味」の練習問題を、ごはんと理解テストに分ける（2026-10-31）。

★なぜ（★2026-10-30 オーナー「とりあえず、こちら側の会話をしっかり理解してくれるのが良い／返答は下手でも」
  「とにかく理解してくれれば、色んな形に組み込める」）
  ★いままでのごはんには「この一言は何をしてほしいのか」を書いた物が1つも無かった。
  ★Qwen3-8B（Apache 2.0）に一言・意味・短い返事・4択の問いを作らせ、
    ★同じ頭に一言と問いだけを見せて答えが合った物だけを残した（C:/dev/realu_kaggle/gen2）。
  ★★掟の変更（★2026-10-31 オーナーが A を選んだ）：
    ★「外のモデルの知識を入れない」を、この練習問題に限って緩めた。

★出すもの:
  food/imi.txt.gz   … ごはん（★make_pantry.py が imi.txt として棚に入れる）
  imi_test.jsonl    … 理解テスト（★ごはんに入れない。★bench_imi.py が測る）

使い方: python to_imi.py samples.jsonl [samples2.jsonl …]
"""
import gzip
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
N_TEST = int(os.environ.get("REALU_IMI_TEST", 300))
NL = "\n"
KEYS = ("種類", "したい事", "気持ち", "対象", "いつ", "聞かれている事")


def prompt(x):
    """★テストとごはんで**同じ形**にする（★形がずれたら測れない）。"""
    return "「" + x["utt"] + "」" + NL + "問い：" + x["quiz"]["q"] + "　答え："


def food(x):
    m = x.get("meaning") or {}
    imi = "。".join("%sは%s" % (k, m.get(k) or "なし") for k in KEYS) + "。"
    q = x["quiz"]
    return NL.join([prompt(x) + q["choices"][q["answer"]],
                    "意味：" + imi,
                    "返事「" + x["reply"] + "」"])


def main():
    xs, seen = [], set()
    for p in sys.argv[1:]:
        for ln in open(p, encoding="utf-8"):
            try:
                x = json.loads(ln)
            except Exception:
                continue
            if not x.get("checked") or x["utt"] in seen:
                continue
            seen.add(x["utt"])
            xs.append(x)
    random.Random(1031).shuffle(xs)
    test, eat = xs[:N_TEST], xs[N_TEST:]
    with open(os.path.join(HERE, "imi_test.jsonl"), "w", encoding="utf-8") as f:
        for x in test:
            q = x["quiz"]
            f.write(json.dumps({"p": prompt(x), "c": q["choices"], "a": q["answer"],
                                "ask": x.get("ask", "")}, ensure_ascii=False) + NL)
    os.makedirs(os.path.join(HERE, "food"), exist_ok=True)
    with gzip.open(os.path.join(HERE, "food", "imi.txt.gz"), "wt", encoding="utf-8") as f:
        f.write((NL + NL).join(food(x) for x in eat) + NL)
    print("★練習問題 %d 件 → テスト %d / ごはん %d" % (len(xs), len(test), len(eat)))


if __name__ == "__main__":
    main()
