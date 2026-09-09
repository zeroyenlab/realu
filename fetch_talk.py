# -*- coding: utf-8 -*-
"""★★★ごはん その6 ── ★人が実際に話した言葉。

★★★なぜこれが要るか
  ★いままで食べたものは、ほとんど「書き言葉」だった:
    法令・判例・Wikipedia・web ＝ ★全部が説明文
    国会 ＝ 話し言葉だが★硬い質疑
    青空 ＝ 会話はあるが★明治〜昭和の文語混じり
  ★★★**現代の、ふつうの会話が1文字も無かった。**
  ★「そうですね、明日も涼しいと聞きました」みたいな文を、一度も読んでいない。

★★★使ってよい根拠（一次情報で確認済み）
  ★3つとも **CC BY-SA 4.0**（HuggingFace のデータセットカードと GitHub で確認）
    → ★出典表示が要る（★このファイルと web に残す）
    → ★同じライセンスで公開が要る（★だからごはんは鍵をかけてしまう）
  ★★RealPersonaChat の利用指針（★守る）:
    ・個人を特定しようとしない
    ・特定の話者になりすまさない
    ・属性や性格を推定しない
  → ★話者は AA / AB などの記号のみ。★元から個人が分からない形。

★★取らないもの
  ★RealPersonaChat の中には **GPT-3.5 / GPT-4 が書いた対話**も入っている
    （llm_dialogue_system/ 以下）。
  → ★★★取らない。★レアルの掟は「外のモデルの知識を入れない」。
"""
import gzip
import io as _io
import json
import os
import re
import sys
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.environ.get("REALU_WORK", os.path.join(HERE, "work"))
OUT = os.path.join(WORK, "talk.txt.gz")
DONE = os.path.join(WORK, "talk_done.txt")
UA = "RealuSeedFetcher/0.1 (+https://realu.pages.dev) python-urllib"
NL = chr(10)

SRC = {
    "rpc": ("RealPersonaChat",
            "https://github.com/nu-dialogue/real-persona-chat"
            "/archive/refs/tags/v1.0.0.zip"),
    "jmw": ("JMultiWOZ",
            "https://github.com/nu-dialogue/jmultiwoz"
            "/raw/master/dataset/JMultiWOZ_1.0.zip"),
    "jcre3": ("J-CRe3",
              "https://github.com/riken-grp/J-CRe3/archive/refs/heads/main.zip"),
}

# ★★J-CRe3 の書き起こしに混ざる注釈を落とす
RUBY = re.compile(r"[{]([^|{}]*)[|][^{}]*[}]")   # ★{一番|いちばん|いちだん} → 一番
TAG = re.compile(r"<[^>]{0,12}>")                # ★<H> など


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=300) as r:
        return r.read()


def clean(t):
    t = RUBY.sub(lambda m: m.group(1), t)
    t = TAG.sub("", t)
    return t.strip()


def from_rpc(z):
    """★人が話した所だけ。★AIが書いた対話（llm_dialogue_system/）は取らない。"""
    out = []
    names = [n for n in z.namelist()
             if "/real_persona_chat/dialogues/" in n and n.endswith(".json")]
    for n in names:
        try:
            j = json.loads(z.read(n).decode("utf-8"))
        except Exception:
            continue
        lines = []
        for u in (j.get("utterances") or []):
            t = clean(u.get("text") or "")
            who = str(u.get("interlocutor_id") or "")[:4]
            if t:
                lines.append(who + "「" + t + "」")
        if len(lines) >= 4:
            out.append(NL.join(lines))
    return out


def from_jmw(z):
    """★用件を伝える対話。★お店を探す・予約する、のような往復。"""
    out = []
    try:
        j = json.loads(z.read("JMultiWOZ_1.0/dialogues.json").decode("utf-8"))
    except Exception:
        return out
    for did, d in (j.items() if isinstance(j, dict) else []):
        turns = d.get("turns") or d.get("dialogue") or []
        lines = []
        for t in turns:
            s = clean(t.get("utterance") or t.get("text") or "")
            who = (t.get("speaker") or "")[:6]
            if s:
                lines.append(("客" if who.upper().startswith("U") else "店")
                             + "「" + s + "」")
        if len(lines) >= 4:
            out.append(NL.join(lines))
    return out


def from_jcre3(z):
    """★「それ」「あれ」が目の前の物を指す会話。★量は少ないが、他に無い。"""
    out = []
    # ★★★-hh- 付きは**同じ場面の別版**（実測: 同じ場面で ロボット18/主人12 と 19/13）。
    #   ★両方取ると二重になる。★新しい方（-hh- なし）だけ取る。
    #   ★念のため中身でも重複を見る（★版が増えても壊れないように）。
    names = [n for n in z.namelist()
             if "/transcriptions/" in n and n.endswith(".txt")
             and "-hh-" not in n]
    seen = set()
    for n in names:
        # ★★★ファイルは**時刻順に並んでいない**（話者ごとにまとまっている）。
        #   ★そのまま読むと会話が壊れる（実測: ロボットの独話19連発に見えた）。
        #   → ★★開始時刻で並べ直す。★これで往復になる。
        rows = []
        for ln in z.read(n).decode("utf-8", "replace").split(NL):
            parts = ln.split(chr(9))
            if len(parts) < 4:
                continue
            who = clean(parts[0])[:6]
            t = clean(parts[-1])
            if not (t and who):
                continue
            try:
                at = float(parts[3])
            except Exception:
                at = 0.0
            rows.append((at, who, t))
        rows.sort(key=lambda r: r[0])
        lines = [w + "「" + t + "」" for _, w, t in rows]
        if len(lines) >= 4:
            body = NL.join(lines)
            key = body[:200]
            if key in seen:      # ★同じ場面が二重に入らないように
                continue
            seen.add(key)
            out.append(body)
    return out


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    os.makedirs(WORK, exist_ok=True)
    try:
        import learn as L
        safe = L.safe
    except Exception:
        def safe(_s):
            return True

    try:
        with open(DONE, encoding="utf-8") as f:
            done = set(f.read().split())
    except Exception:
        done = set()

    picks = {"rpc": from_rpc, "jmw": from_jmw, "jcre3": from_jcre3}
    got_any = False
    # ★★★2026-09-09: ここで**無条件に**追記モードで開いていた。
    #   ★Python の gzip は「開いて閉じる」だけで★**空のメンバー34バイト**を書く。
    #   ★取るものが無い回でも talk.txt.gz が 34 バイト増えていた。
    #   ★★grow.yml は「ごはんの合計バイトが変わったら棚を作り直す」ので、
    #     ★★毎回 2GB の棚を **28分**かけて作り直していた（★実測 #38/#39/#40 とも +34）。
    #   → ★取るものがある時だけ開く。
    todo = [k for k in SRC if k not in done]
    for key in SRC:
        if key in done:
            print("★%s はもう持っている" % SRC[key][0], flush=True)
    if todo:
      with gzip.open(OUT, "at", encoding="utf-8", newline=NL) as f:
        for key in todo:
            title, url = SRC[key]
            print("★%s をもらいに行く…" % title, flush=True)
            try:
                z = zipfile.ZipFile(_io.BytesIO(fetch(url)))
                blocks = picks[key](z)
            except Exception as e:
                print("  ★取れなかった: %s（次の回にまた試す）"
                      % type(e).__name__, flush=True)
                continue
            n = chars = 0
            for b in blocks:
                # ★★露骨な文は入れない（★learn.py と同じ網）
                body = NL.join(x for x in b.split(NL) if safe(x))
                if len(body) < 40:
                    continue
                # ★★★出典を必ず残す（CC BY-SA の帰属表示）
                f.write(NL + "<会話 " + title + ">" + NL + body + NL)
                n += 1
                chars += len(body)
            print("  ★%d 本 / %.1f 万字" % (n, chars / 10000), flush=True)
            done.add(key)
            got_any = True
            with open(DONE, "w", encoding="utf-8") as g:
                g.write(" ".join(sorted(done)))

    size = os.path.getsize(OUT) / 1024 / 1024 if os.path.exists(OUT) else 0
    print("★★人の会話: いま持っている %.1f MB / 取れた元: %s"
          % (size, " ".join(sorted(done)) or "なし"), flush=True)
    if not got_any and done:
        print("★新しく足すものは無かった", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
