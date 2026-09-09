# -*- coding: utf-8 -*-
"""★★★いまの数字を玄関（/api/state）に置くだけの係。

★★なぜ要るか
  ★家（index.html）は**2時間に一度**しか建て直せない（★Cloudflare の無料枠が月500回）。
  ★だから数字は玄関に置いて、★**家が開くたびに読みに来る**形にしてある。
  ★その玄関を更新していたのは古い「web漁り」係（learn.py）だった。
  ★★2026-09-09 に5分ごとの係を「測る係」へ作り替えたとき、★この配線ごと外れた
    （`fd63119`）。★結果、★サイトの数字が 2026-09-08T19:25Z で止まっていた。

★★することは1つだけ
  ★knowledge.json と design.json と growth.json を読んで、★`learn.tell()` に渡す。
  ★★web は読まない。★何も書き換えない。★玄関に置くだけ。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import learn   # noqa: E402  ★定数しか無いので import して安全（★main は __main__ ガードの中）


def main():
    if not os.environ.get("REALU_DOOR_KEY"):
        print("★玄関の鍵が無い。★何もしない")
        return 0
    k = learn.load(learn.K, {"items": [], "read": {}})
    d = learn.load(learn.D, {})
    if not k.get("items"):
        print("★知識がまだ無い。★何もしない")
        return 0
    learn.tell(k, d)   # ★中で成否を印字する
    return 0


if __name__ == "__main__":
    sys.exit(main())
