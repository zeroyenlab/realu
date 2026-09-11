# -*- coding: utf-8 -*-
"""★★★ことばの単位を、自分のごはんから切り出す。

★★★なぜ既存のトークナイザを使わないか
  ★既存のトークナイザは、★語彙そのものが**外の世界の知識**。
  ★「Twitter」「大統領」みたいな単位が最初から入っていたら、★それはもう何かを知っている。
  → ★★**自分が食べたものからだけ**単位を作る。★外の語彙は1つも入らない。

★★★なぜ文字単位をやめるか
  ★文字単位は純粋だが、★効率を2〜3倍捨てている。
  ★「日本語」を4つ使って表すのと、1つで表すのとでは、★同じ容量で見渡せる範囲が変わる。
  → ★★自分のコーパスから単位を学べば、★純度を保ったまま効率だけ上がる。

★★バイトから始めるので、★★★知らない文字が存在しない（★何でも読める）。
"""
import gzip
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.environ.get("REALU_WORK", os.path.join(HERE, "work"))
TOK = os.environ.get("REALU_TOK", os.path.join(WORK, "tok.json"))
# ★★★16,000 は、この大きさの頭には**大きすぎた**（実測）:
#   文字4,500 → 全体 2.64M / 表 0.86M（33%） / 1歩 1.68秒
#   BPE16,000 → 全体 4.84M / 表 3.07M（★63%） / 1歩 2.74秒
#   ★増えた 2.2M は**全部が引き当て表**。★考える所（1.77M）は1ミリも増えていない。
#   ★別プロジェクトの日本語研究の結論と同じ:「軽さの本体は語彙を捨てること」
VOCAB = int(os.environ.get("REALU_VOCAB", 6000))
# ★★★2.5億字は**メモリで死ぬ**（★2026-09-08 実測: runner ごと落ちた）。
#   ★日本語は空白が無いので、★1行がまるごと1カタマリになる（実測: 56字→6個、最長81バイト）。
#   ★英語は単語が何度も出るので数え上げが小さく済むが、★日本語は**ほぼ全部が一度きり**。
#   → ★数え上げの表が巨大になって、★16GBを食い尽くす。
SAMPLE = int(os.environ.get("REALU_TOK_SAMPLE", 50_000_000))


# ★★日本語の切れ目（★ここをまたぐ「語」は、ほぼ無い）
SPLIT = re.compile("([、。，．！？「」『』（）・：；　 ]+)")


def feed():
    """★自分のごはんを少しずつ渡す。★全部メモリに載せない。"""
    got = 0
    for name in ("laws.txt", "hanrei.txt", "wiki.txt", "web.txt", "kokkai.txt", "aozora.txt"):
        for p in (os.path.join(WORK, name + ".gz"), os.path.join(WORK, name)):
            if not os.path.exists(p):
                continue
            op = gzip.open if p.endswith(".gz") else open
            with op(p, "rt", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if len(line) < 8:
                        continue
                    got += len(line)
                    # ★★★句読点で切ってから渡す。
                    #   ★1行まるごとだと「一度きりの長い並び」になって数え上げが爆発する。
                    #   ★切ると短くて何度も出るカタマリになる ＝ 数え上げが小さくなる。
                    #   ★切れ目をまたぐ単位は作れなくなるが、★句読点をまたぐ語はほぼ無い。
                    for part in SPLIT.split(line):
                        if part:
                            yield part
                    if got > SAMPLE:
                        return
            break


def main():
    # ★★表示だけで死なないように（★端末の文字コードは選べない）
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    os.makedirs(WORK, exist_ok=True)
    if os.path.exists(TOK):
        print("★ことばの単位はもう持っている")
        return 0

    from tokenizers import Tokenizer, decoders, models, pre_tokenizers, trainers

    tok = Tokenizer(models.BPE(unk_token=None))
    # ★★バイト単位から始める → ★知らない文字が存在しない
    tok.pre_tokenizer = pre_tokenizers.ByteLevel(add_prefix_space=False)
    tok.decoder = decoders.ByteLevel()
    trainer = trainers.BpeTrainer(
        vocab_size=VOCAB,
        show_progress=True,
        initial_alphabet=pre_tokenizers.ByteLevel.alphabet(),
        special_tokens=[],
    )
    print("★自分のごはんから、ことばの単位を切り出す（%d 個）…" % VOCAB, flush=True)
    tok.train_from_iterator(feed(), trainer=trainer)
    tok.save(TOK)

    # ★★どれだけ短くなったか測る
    probe = "日本語は膠着語であり、著作権は著作物を創作した者に与えられる権利の総称である。"
    ids = tok.encode(probe).ids
    print("★できた: 語彙 %d / 見本 %d 文字 → %d 個（★%.2f 文字ぶんが1個）"
          % (tok.get_vocab_size(), len(probe), len(ids), len(probe) / max(1, len(ids))),
          flush=True)
    print("★切れ目:", " | ".join(tok.decode([i]) for i in ids[:18]), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
