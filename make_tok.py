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
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.environ.get("REALU_WORK", os.path.join(HERE, "work"))
TOK = os.path.join(WORK, "tok.json")
VOCAB = int(os.environ.get("REALU_VOCAB", 16000))
SAMPLE = int(os.environ.get("REALU_TOK_SAMPLE", 250_000_000))   # ★学習に使う文字数


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
                    yield line
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
