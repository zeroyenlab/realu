"""★★★古い置き場（Actions cache）のうち、捨ててよいものを選ぶ。

★★cache の上限は **10GB**。★超えると GitHub が**黙って**古いものから消す。
★★★2026-09-15 の実測: 9.84GB まで埋まり、★`work`（1回 3.09GB）が3つで 9.27GB。
　★押し出されて **3系統の頭がほとんど消えていた**（★L1 の頭は全滅）。
★★頭が消えても Release から取り戻せるので**転ばない**。★だから誰も気づかない ──
　★★★転ばないまま、★毎回ちがう頭から学び直すことになる。

★選び方: ★**同じ名前の系統ごとに、一番新しい1つだけ残す**。
　★取り出しは `restore-keys` の前方一致なので、★一番新しいものしか使われない。
　★古いものは容量を食うだけ。

使い方:
  gh api "repos/$REPO/actions/caches?per_page=100" | python prune_caches.py
      → ★捨てるものを「id<タブ>名前」で1行ずつ出す
  gh api "repos/$REPO/actions/caches?per_page=100" | python prune_caches.py --size
      → ★いまの合計だけを出す
"""
import io
import json
import sys

# ★系統ごとに1つずつ残す前方一致の名前
KEEP_NEWEST = (
    "realu-work-",
    "realu-brain-L1-",
    "realu-brain-L2-",
    "realu-brain-L3-",
)
LIMIT_MB = 10000


def load(fp):
    try:
        d = json.load(fp)
    except Exception as e:
        print("★置き場の一覧が読めなかった（%s）。★何も捨てない" % type(e).__name__,
              file=sys.stderr)
        return None
    cs = d.get("actions_caches")
    return cs if isinstance(cs, list) else None


def main():
    cs = load(io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8"))
    if cs is None:
        return 1
    total = sum(c.get("size_in_bytes") or 0 for c in cs)
    if "--size" in sys.argv:
        print("★置き場: %d MB / 上限 %d MB（★%d 個）"
              % (total // 10**6, LIMIT_MB, len(cs)))
        return 0

    print("★いまの置き場: %d MB / 上限 %d MB（★%d 個）"
          % (total // 10**6, LIMIT_MB, len(cs)), file=sys.stderr)
    for pre in KEEP_NEWEST:
        group = sorted((c for c in cs if (c.get("key") or "").startswith(pre)),
                       key=lambda c: c.get("created_at") or "")
        # ★★一番新しい1つは必ず残す。★1つ以下なら何もしない
        for c in group[:-1]:
            print("%s\t%s" % (c.get("id"), c.get("key")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
