# -*- coding: utf-8 -*-
"""★★★測る係 ── ★勘で決めた設定を、★数字で確かめる。

★★★なぜ要るか
  ★レアルは、★**測っていない設定**をいくつも使っている:
    ・Muon（最適化手法）      … A/Bの片側しか測っていない
    ・ループ                  … 既定オフのまま
    ・記憶の三層 50/30/20      … 論文の数字。★レアルで測っていない
    ・深さと幅の比 ASPECT=48   … ★GPT-2 の見た目を真似ただけ
    ・学習率の上げ下げ          … 勘
  ★★誰も確かめないまま、★毎日その設定で学び続けている。

★★★どうするか
  ★5分の枠で、★**同じ条件で2つ回して比べる**。
  ★1回4分 × 288回/日 ＝ ★1日1,152分ぶんの実験ができる。

★★★守ること
  ★① レアルの本物の頭には触らない。★別の場所で小さいのを作って測る。
  ★② 種を固定して、★同じ土俵で比べる（★片方だけ運が良い、を防ぐ）。
  ★③ 種を3つ変えて3回やる。★★1回だけの差は信じない
     （★過去の研究で「種が20pt振れる」と分かっている）。
  ★④ 結果は追記だけ。★★都合の悪い結果を消さない。
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.environ.get("REALU_WORK", os.path.join(HERE, "work"))
OUT = os.path.join(HERE, "ab_results.json")
NL = chr(10)

STEPS = int(os.environ.get("REALU_AB_STEPS", 300))
SEEDS = int(os.environ.get("REALU_AB_SEEDS", 3))
BUDGET = float(os.environ.get("REALU_AB_BUDGET", 3.5)) * 60   # ★秒

# ★★★測ること。★上から順に、★終わったものは飛ばす。
#   ★"a" と "b" は grow.py に渡す設定の差。
TESTS = [
    {"id": "loop2",
     "why": "★ループ2周は効くか（★いま既定オフ。★58%のパラメータで loss +0.10 という測定がある）",
     "a": {}, "b": {"REALU_USE_LOOP": "1", "REALU_MAX_LOOPS": "2"}},
    {"id": "tier",
     "why": "★記憶の三層 50/30/20 は正しいか（★論文の数字。★レアルで測っていない）",
     "a": {}, "b": {"REALU_SHORT_P": "0.34", "REALU_MID_P": "0.33"}},
    {"id": "aspect",
     "why": "★4層より深くしてよいか（★ASPECT=48 は GPT-2 の見た目を真似ただけ）",
     "a": {"REALU_LAYERS": "4"}, "b": {"REALU_LAYERS": "8"}},
    {"id": "lr",
     "why": "★学習率 3e-4 は妥当か（★勘で決めた）",
     "a": {}, "b": {"REALU_LR": "6e-4"}},
    {"id": "dup",
     "why": "★同じ行を3回までにしているのは妥当か",
     "a": {}, "b": {"REALU_DUP_MAX": "1"}},
    {"id": "ctx",
     "why": "★見渡せる幅 256 を 512 にすると効くか（★1歩は重くなる）",
     "a": {"REALU_CTX": "256"}, "b": {"REALU_CTX": "512"}},
]


def load():
    try:
        with open(OUT, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"done": {}, "log": []}


def one(env, seed, tmp):
    """★1本まわして loss を返す。★本物の頭には触らない。"""
    import subprocess
    e = dict(os.environ)
    e.update({
        "REALU_WORK": WORK,          # ★ごはん（棚）は共有。★読むだけ
        "REALU_STEPS": str(STEPS),
        "REALU_EVAL": str(max(50, STEPS // 4)),
        "REALU_SEED": str(seed),
        "REALU_AB_TMP": tmp,         # ★頭はここに書く（★本物と別）
        "REALU_THREADS": "4",
        "REALU_TIME_BUDGET": "999",
    })
    e.update(env)
    r = subprocess.run([sys.executable, "-u", "ab_one.py"],
                       cwd=HERE, env=e, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=1200)
    for ln in (r.stdout or "").split(NL):
        if ln.startswith("LOSS="):
            try:
                return float(ln[5:])
            except Exception:
                pass
    return None


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    res = load()
    t0 = time.time()
    tmp = os.path.join(WORK, "ab_tmp")
    os.makedirs(tmp, exist_ok=True)

    for t in TESTS:
        if t["id"] in res["done"]:
            continue
        print("★測る: %s" % t["id"], flush=True)
        print("   %s" % t["why"], flush=True)
        a_all, b_all = [], []
        for s in range(SEEDS):
            if time.time() - t0 > BUDGET:
                print("   ★時間切れ。★次の回に続ける（★ここまでは捨てる）", flush=True)
                return 0
            a = one(t["a"], 1000 + s, tmp)
            b = one(t["b"], 1000 + s, tmp)
            if a is None or b is None:
                print("   ★測れなかった（種 %d）" % s, flush=True)
                continue
            a_all.append(a)
            b_all.append(b)
            print("   種%d  A %.4f  B %.4f  差 %+.4f" % (s, a, b, b - a), flush=True)
        if len(a_all) < 2:
            print("   ★種が2つ揃わなかった。★次の回にやり直す", flush=True)
            return 0
        ma = sum(a_all) / len(a_all)
        mb = sum(b_all) / len(b_all)
        diffs = [y - x for x, y in zip(a_all, b_all)]
        spread = max(diffs) - min(diffs)
        # ★★★判定は**厳しく**する。
        #   ★過去の研究で「★種が20pt振れる」と分かっている。
        #   ★差がばらつきと同じくらいなら、★それは差ではない。
        #   → ★★全部の種で**同じ向き**に出て、かつ差がばらつきより大きい時だけ言う。
        same_way = all(x < 0 for x in diffs) or all(x > 0 for x in diffs)
        big = abs(mb - ma) > spread
        if same_way and big:
            verdict = "★Bが良い" if mb < ma else "★Aが良い"
        elif same_way:
            verdict = "★たぶん%s（★向きは揃ったが、差が小さい）" % (
                "B" if mb < ma else "A")
        else:
            verdict = "★わからない（★種で向きが変わる＝それは差ではない）"
        print("   ★★A %.4f / B %.4f / 差 %+.4f / 種のばらつき %.4f → %s"
              % (ma, mb, mb - ma, spread, verdict), flush=True)
        res["done"][t["id"]] = {
            "why": t["why"], "a": ma, "b": mb, "diff": mb - ma,
            "spread": spread, "verdict": verdict,
            "seeds": len(a_all), "steps": STEPS,
            "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "aEnv": t["a"], "bEnv": t["b"],
        }
        res["log"].append({"id": t["id"], "at": res["done"][t["id"]]["at"],
                           "diff": mb - ma, "verdict": verdict})
        with open(OUT, "w", encoding="utf-8", newline=NL) as f:
            json.dump(res, f, ensure_ascii=False, indent=1)
            f.write(NL)
        print("   ★書き残した", flush=True)
        return 0

    print("★測ることはもう無い（%d 件ぶん済み）" % len(res["done"]), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
