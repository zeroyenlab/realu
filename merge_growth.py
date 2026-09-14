"""★★★成長の記録を、上書きではなく**混ぜて**残す。

★次の回は、前の回が記録を push し終える前に checkout してしまうことがある
  （★L1 が終わった時点で次を呼ぶので、★L2/L3 がまだ書いている最中）。
★そのまま自分の版を cp すると、★**先に書かれていた1回ぶんが黙って消える**。
  ★2026-09-14 に実際に消えた: #165 の L2 の記録が #166 に上書きされた。
★★脳は cache と Release にあるので無事。★消えるのは「何が起きたか」の記録だけ。
  ★だから気づきにくい ── ★★育ちの曲線に穴が空くだけで、誰も転ばない。

使い方: python merge_growth.py <この回の記録> <origin の記録> <書き出し先>
"""
import io
import json
import sys


def load(path):
    try:
        with io.open(path, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else None
    except Exception:
        return None


def last_at(d):
    rs = (d or {}).get("runs") or []
    return rs[-1].get("at") or "" if rs else ""


def main():
    mine_p, theirs_p, out_p = sys.argv[1], sys.argv[2], sys.argv[3]
    mine = load(mine_p)
    if mine is None:
        print("★この回の記録が読めない。★何もしない")
        return 1
    theirs = load(theirs_p)

    if theirs is not None:
        # ★★★新しいほうの「体の現在地」を土台にする。
        #   ★bad / layers / nextD / wantWider は**いまの脳の状態**なので、
        #   ★★古い回のものを被せると、★次の回が間違った体を前提に動く。
        base, other = ((mine, theirs) if last_at(mine) >= last_at(theirs)
                       else (theirs, mine))
        seen = {r.get("at") for r in base.get("runs") or []}
        extra = [r for r in (other.get("runs") or []) if r.get("at") not in seen]
        runs = (base.get("runs") or []) + extra
        runs.sort(key=lambda r: r.get("at") or "")
        base["runs"] = runs[-200:]
        # ★★測れなかった回（null）を混ぜない
        ok = [r["val"] for r in base["runs"]
              if isinstance(r.get("val"), (int, float)) and r["val"] == r["val"]]
        base["bestVal"] = round(min(ok), 4) if ok else None
        if extra:
            print("★★先に書かれていた記録 %d 件を拾った（★%s）"
                  % (len(extra), " / ".join(r.get("at") or "?" for r in extra)))
        mine = base

    with io.open(out_p, "w", encoding="utf-8", newline="\n") as f:
        json.dump(mine, f, ensure_ascii=False, indent=1)
        f.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
