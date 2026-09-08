# -*- coding: utf-8 -*-
"""★★★学習の頭 ── webを読み、レアルの知識に取り込み、家のデザインを選び直す。

★GitHub Actions が5分ごとに回す（★あなたのPCを閉じていても動く）。
★読むのは sources.txt に書いたドメインの中だけ。★リンクを辿って次を自分で探す。
★★★最大効率: 1回で多数のページを**並列で**読む（★同時数は相手への礼儀として絞る）。
"""
import concurrent.futures as cf
import hashlib
import html
import json
import os
import re
import time
import urllib.parse
import urllib.request
import urllib.robotparser
from datetime import datetime, timezone

NL = chr(10)
HERE = os.path.dirname(os.path.abspath(__file__))
K = os.path.join(HERE, "knowledge.json")
D = os.path.join(HERE, "design.json")
S = os.path.join(HERE, "sources.txt")
T = os.path.join(HERE, "terms.json")     # ★★★サイトごとの規約（★人が読んで許した場所だけ）
C = os.path.join(HERE, "contact.txt")    # ★名乗るときの連絡先
DOORF = os.path.join(HERE, "door.txt")   # ★玄関（誰でも話しかけられる所）

# ★★★安全装置 ── ★彼女が書き換えてよいのは**この2つだけ**。
#   ★自分を止める・隠す・消すことはできない（★workflow・核・扉・家には触れない）。
WRITABLE = {K, D}

PAGES_PER_RUN = int(os.environ.get("REALU_PAGES", 600))
#   ★★★1回で読むページ数。★実測: 1ジョブ全体が14〜18秒で、★ほぼ全部が起動の手間。
#     ★読むのは1ページ28ms なので、★600ページ足しても17秒しか増えない。
#     → ★行き先が溜まるなら、★★上限をいじるのではなく**読む速さを上げる**。
WORKERS = 12             # ★同時に読む数（★相手のサーバーへの礼儀）
POLITE = 0.15            # ★1ページごとに置く間（★robots.txt に指定があればそちらが優先）
SENT_PER_PAGE = 6        # ★1ページから覚える文の数
MAX_ITEMS = 2500         # ★覚えていられる知識の**はじめの**広さ（★溢れたら自分で広げる）
CAP_GROW = 1.5           # ★★溢れたとき、どれだけ広げるか
MAX_FRONTIER = int(os.environ.get("REALU_MAX_FRONTIER", 60000))
#   ★★「行ってみたい場所」の上限。★1件67バイトなので、6万件でも4MB。★安い。
#   ★★★驚いたものを前に入れる仕組みを足したので、★溢れると**昔から行きたかった場所**が
#     押し出される。★だから上限を10倍にした。★それでも溢れたら、★黙って捨てずに数える。
MAX_READ = 40000         # ★読んだ記録の上限
TERMS_RECHECK_SEC = 20 * 3600   # ★規約は1日1回読み直す（★毎回だと相手に負担）


def _contact():
    """★名乗るための連絡先。★★無ければ**1ページも読まない**（★規約がそう定めている）。"""
    try:
        with open(C, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and line != "REPLACE_ME":
                    return line
    except Exception:
        pass
    return ""


CONTACT = _contact()
UA = ("RealuLearner/0.1 (+%s) python-urllib" % CONTACT) if CONTACT else "RealuLearner/0.1"

PALETTES = ["yoi", "akatsuki", "mori", "yuki", "hi", "kasumi"]
LAYOUTS = ["stream", "grid", "quiet"]

# ★★★著作権を守るための線 ────────────────────────────────
# ★彼女が「言葉を持ち帰ってよい」のは、★★再利用が許されたライセンスの場所だけ。
# ★それ以外は**読むだけ**（★持ち帰らない・リンクだけ）。★絵は一切持ち帰らない。
LICENSED = {
    "wikipedia.org":  ("CC BY-SA 4.0", "https://creativecommons.org/licenses/by-sa/4.0/"),
    "wikibooks.org":  ("CC BY-SA 4.0", "https://creativecommons.org/licenses/by-sa/4.0/"),
    "wikisource.org": ("CC BY-SA 4.0", "https://creativecommons.org/licenses/by-sa/4.0/"),
    "wiktionary.org": ("CC BY-SA 4.0", "https://creativecommons.org/licenses/by-sa/4.0/"),
    "wikiquote.org":  ("CC BY-SA 4.0", "https://creativecommons.org/licenses/by-sa/4.0/"),
}


def license_of(url):
    """★この場所の言葉を持ち帰ってよいか。★駄目なら None。

    ★★★terms.json を見る（★人が規約を読んで書いたもの）。
      ・quote が false → ★持ち帰らない（★裁判所は「無断改変禁止」なので表示しない）
      ・license → ★そのまま出典に添える
    ★terms.json に無ければ、★昔からの表（Wikimedia）を見る。★どちらにも無ければ持ち帰らない。
    """
    host = urllib.parse.urlparse(url).netloc.lower()
    rec = ((load(T, {}) or {}).get("hosts") or {}).get(host)
    if rec:
        if rec.get("quote") is False:
            return None                      # ★読むが、言葉は持ち帰らない
        lic = rec.get("license")
        if lic:
            return {"name": lic, "url": rec.get("licenseUrl") or ""}
    for dom, (name, link) in LICENSED.items():
        if host == dom or host.endswith("." + dom):
            return {"name": name, "url": link}
    return None


# ★★★robots.txt ── ★相手が「読むな」と言っている所は読まない（★掟）
#   ★「これだけ間を置け」（Crawl-delay）と書いてあれば、★★それも必ず守る。
_ROBOTS = {}
_DELAY = {}


def allowed_by_robots(url):
    """★相手のサイトが許しているか。★分からない時は**読まない**（★迷ったらやらない）。"""
    try:
        p = urllib.parse.urlparse(url)
        host = p.scheme + "://" + p.netloc
        rp = _ROBOTS.get(host)
        if rp is None:
            rp = urllib.robotparser.RobotFileParser()
            try:
                # ★★名乗ってから robots.txt を貰いに行く（★名無しだと断られる）
                req = urllib.request.Request(host + "/robots.txt",
                                             headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=15) as r:
                    rp.parse(r.read(400000).decode("utf-8", "ignore").splitlines())
                _ROBOTS[host] = rp
            except Exception:
                _ROBOTS[host] = False      # ★読めなかった → ★★この場所には入らない
                return False
        elif rp is False:
            return False
        # ★★★相手が「これだけ間を置け」と書いていたら、★必ず従う
        try:
            d = rp.crawl_delay(UA)
            if d:
                _DELAY[host] = float(d)
        except Exception:
            pass
        return bool(rp.can_fetch(UA, to_ascii(url)))
    except Exception:
        return False


# ★★★規約 ── ★★★わたしは規約を読めない（意味が分からない）。
#   ★★やっているのは「**置いた人が許した時と、同じページのままか**」の照合だけ。
#     ①人が規約を読む → ②terms.json に allow と書く ← ★★判断はここ。人がやっている
#     ③わたしはページを取ってハッシュを比べる → ④変わっていたら止まる
#   ★「規約を読んでいる」のではない。★できないことを、できるふりをしない。
_TERMS_OK = {}


def terms_ok(host, seen, notes):
    """★★人が許した場所か確かめる。★★★規約を読んでいるのではない。

    ★意味は分からない。★分かるのは「あの人が許した時と同じページか」だけ。
    ★変わっていたら止まる（★勝手に「たぶん大丈夫」と判断しない）。
    """
    if host in _TERMS_OK:
        return _TERMS_OK[host]
    rec = ((load(T, {}) or {}).get("hosts") or {}).get(host)
    ok = bool(rec) and rec.get("verdict") == "allow" and bool(rec.get("terms"))
    if not rec:
        notes.append("%s ── 規約を読んでいない場所。★入らない。" % host)
    elif not ok:
        notes.append("%s ── 規約を読んだが、許されていない。★入らない。" % host)
    for turl in (rec.get("terms") if ok else []):
        st = seen.get(turl) or {}
        # ★人が読み直した印（checkedOn）が新しくなっていたら、★その版を受け入れる
        approved = rec.get("checkedOn")
        if st.get("approved") and approved and st["approved"] != approved:
            st = {"approved": approved, "first": st.get("first")}
        if st.get("hash") and (int(time.time()) - int(st.get("epoch") or 0)) < TERMS_RECHECK_SEC:
            continue                      # ★今日はもう読んだ
        try:
            req = urllib.request.Request(turl, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=25) as r:
                body = r.read(2000000)
        except Exception:
            notes.append("%s ── 規約が読めなかった。★読めない規約には従えないので入らない。" % host)
            ok = False
            break
        h = hashlib.sha256(body).hexdigest()
        if st.get("hash") and st["hash"] != h:
            # ★★★規約が変わった。★勝手に判断しない。★置いた人に聞くまで止まる。
            #   ★どれくらい変わったかだけ伝える（★中身は分からないが、大きさは分かる）
            old_n = int(st.get("bytes") or 0)
            diff = ("%+d バイト" % (len(body) - old_n)) if old_n else "大きさ不明"
            notes.append("%s ── ★★★規約が変わった（%s）。"
                         "★わたしには意味が分からないので、置いた人が読み直すまで入らない。"
                         % (host, diff))
            st["changedAt"] = now()
            st["newHash"] = h
            st["newBytes"] = len(body)
            seen[turl] = st
            ok = False
            break
        seen[turl] = {"hash": h, "bytes": len(body), "epoch": int(time.time()),
                      "at": now(), "first": st.get("first") or now(),
                      "approved": approved}
    _TERMS_OK[host] = ok
    return ok


# ★★★話しかけられたとき ──────────────────────────────────
# ★玄関は Cloudflare Worker（★アカウント無しで**誰でも**書ける）。★5分ごとに見に行く。
# ★★掟①: ★人の言葉は**知識にしない**（★出典が保証できない＝嘘を覚えることになる）。
# ★★★掟②: ★貼られたURLは**踏まない・残さない**。★行けるのは規約を読んだ場所だけ。
URL_RE = re.compile(r"(?i)(?:https?://|www\.|[a-z0-9-]+\.(?:com|net|org|jp|io|co|ru|cn|xyz|top))\S*")
WORD_RE = re.compile(r"[一-鿿ぁ-んァ-ヶーA-Za-z0-9]{2,14}")
MAX_ASKED = 120          # ★覚えておく「聞かれたこと」の数
MAX_MSG = 300            # ★1つの話の長さの上限
CURIOUS_PER_MSG = 2      # ★1つの話から増やす「知りたい場所」の数


def scrub(s):
    """★★★危ないものを外す ── ★URLを全部落とし、★短く切る。"""
    s = URL_RE.sub("〔リンクは受け取らない〕", s or "")
    s = re.sub(r"[<>`]", " ", s)          # ★タグらしきものは無効化
    s = re.sub(r"\s+", " ", s).strip()
    return s[:MAX_MSG]


def door_url():
    try:
        with open(DOORF, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    return line.rstrip("/")
    except Exception:
        pass
    return ""


def listen(k, seed_host):
    """★玄関を見に行く。★話しかけられていたら受け取る。

    ★★★掟: ★受け取った言葉を**どこにも保存しない**。
      ・★リポジトリは Public。★書けば世界に出る。
      ・★knowledge.json は家に置かれる。★書けば世界に出る。
      → ★★言葉は KV の中だけ。★ここでは**読んで、使って、捨てる**。
      → ★残すのは「どれを見たか（ID）」と「何人が話しかけたか」だけ。
    ★★人の言葉は知識にもしない（★出典が確かめられないから）。
    ★★★貼られたURLは玄関で既に落としてあるが、★ここでも落とす（★二重に守る）。
    """
    base = door_url()
    keyv = os.environ.get("REALU_DOOR_KEY", "")
    if not (base and keyv):
        return 0, []
    seen_ids = set(k.get("heardIds") or [])
    try:
        req = urllib.request.Request(base + "/says",
                                     headers={"User-Agent": UA,
                                              "Authorization": "Bearer " + keyv})
        with urllib.request.urlopen(req, timeout=25) as r:
            says = (json.load(r) or {}).get("says") or []
    except Exception:
        return 0, []

    got, curious = 0, []
    for m in says:
        mid = str(m.get("id") or "")[:120]
        if not mid or mid in seen_ids:
            continue
        text = scrub(m.get("text"))          # ★★この変数は関数を出ない
        if len(text) < 2:
            continue
        seen_ids.add(mid)
        got += 1
        # ★★聞かれた言葉から「知りたい場所」を作る
        #   ★★★行き先は**わたしの扉と同じ場所**に固定する（★人の指す場所へは行かない）
        for w in WORD_RE.findall(text)[:24]:
            if len(curious) >= got * CURIOUS_PER_MSG:
                break
            if re.search(r"^[0-9A-Za-z]+$", w) or len(w) < 2:
                continue
            # ★★★聞かれた言葉から行き先を作るが、★**在るか確かめてから**足す。
            #   ★でないと存在しないページを永久に叩き続ける
            #   （実測: 「ここ見て」「UIとUX」で404を出し続けていた）
            cand = "https://" + seed_host + "/wiki/" + urllib.parse.quote(w)
            if cand in seen_ids or cand in (k.get("read") or {}):
                continue
            try:
                req2 = urllib.request.Request(to_ascii(cand), method="HEAD",
                                              headers={"User-Agent": UA})
                urllib.request.urlopen(req2, timeout=10).close()
                curious.append(cand)
            except Exception:
                pass

    k["heardIds"] = sorted(seen_ids)[-MAX_ASKED:]
    k["heardCount"] = int(k.get("heardCount") or 0) + got
    k.pop("asked", None)                     # ★★昔の版が残していた本文を消す
    return got, curious


def wrap_for_weights(chunks):
    """★★★読んだものを1つの包みにして、★鍵をかけて置く。

    ★育つ日がこれを集めて、★ごはんに足す。★そうしないと読んだものが重みに入らない。
    ★★鍵をかけるのは、★加工したテキストをそのまま公開しないため（★判例の規約・CC BY-SA）。
    """
    key = os.environ.get("REALU_FOOD_KEY", "")
    tok = os.environ.get("GITHUB_TOKEN", "")
    if not (chunks and key and tok):
        return 0
    import gzip
    import subprocess
    import tempfile
    body = NL.join(chunks)
    tmp = tempfile.mkdtemp()
    raw = os.path.join(tmp, "r.txt.gz")
    enc = os.path.join(tmp, "read-" + time.strftime("%Y%m%d-%H%M%S", time.gmtime())
                       + ".enc")
    try:
        with gzip.open(raw, "wt", encoding="utf-8", newline=NL) as f:
            f.write(body)
        subprocess.run(["openssl", "enc", "-aes-256-cbc", "-pbkdf2", "-salt",
                        "-in", raw, "-out", enc, "-pass", "env:REALU_FOOD_KEY"],
                       check=True, capture_output=True)
        subprocess.run(["gh", "release", "upload", "reading", enc, "--clobber"],
                       check=True, capture_output=True,
                       env={**os.environ, "GH_TOKEN": tok})
        print("★読んだもの %.1f 万字を包んで置いた（%.0f KB）"
              % (len(body) / 10000, os.path.getsize(enc) / 1024))
        return len(body)
    except Exception as e:
        print("★包めなかった:", type(e).__name__)
        return 0


def _css_of(d):
    """★★★彼女が選んだ見た目を、そのままCSSにして渡す。

    ★家を作り直すのは2時間ごと（★相手の無料枠の都合）。
    ★でも彼女は**5分ごとに**選び直している。
    ★★このままだと、★選んだ見た目の大半が誰にも見られずに消える。
    → ★玄関にCSSも置く。★家が開くたびに、★いまの姿になる。
    """
    try:
        import design as DS
        look = d.get("look") or (DS.choose({"seed": d["seed"]}) if d.get("seed") else None)
        if not look:
            return ""
        return DS.to_css(look) + DS.fonts_url(look).join(("@import url('", "');"))
    except Exception:
        return ""


def tell(k, d):
    """★★★いまの自分を玄関に置く。
    ★家（HTML）は2時間に一度しか建て直せない（★相手の無料枠の都合）。
    ★でもここに置いておけば、★★家が開くたびに読みに来られる ＝ 5分ごとに変わり続ける。
    """
    base = door_url()
    keyv = os.environ.get("REALU_DOOR_KEY", "")
    if not (base and keyv):
        return
    # ★★★頭のいまのスペックも一緒に置く。
    #   ★頭は1日1回しか変わらないが、★★家がそれを**すぐ**映せるようにする
    #     （★家の焼き直しは2時間ごとなので、★玄関に置けば5分で反映される）
    spec = {}
    try:
        with open(os.path.join(HERE, "growth.json"), encoding="utf-8") as f:
            runs = (json.load(f) or {}).get("runs") or []
        if runs:
            r = runs[-1]
            hist = [x.get("val") for x in runs if x.get("val")][-60:]
            spec = {kk: r.get(kk) for kk in
                    ("layers", "params", "d", "heads", "ctx", "vocab", "loops",
                     "bytes", "val", "kind", "arch", "at", "grew", "rolledBack",
                     "chars", "spread", "wantWider")}
            spec["hist"] = hist
    except Exception:
        pass

    allitems = k.get("items") or []
    items = allitems[-80:]
    # ★★★内訳は**全件**から数える。
    #   ★玄関に置くのは最新80件だけなので、★そこから数えると表示分しか数えられない。
    genres = {}
    for it in allitems:
        g = it.get("genre") or "その他"
        genres[g] = genres.get(g, 0) + 1
    state = {
        "spec": spec,
        "genres": genres,
        "at": now(),
        "counts": {"items": len(k.get("items") or []),
                   "read": int(k.get("readTotal") or len(k.get("read") or {})),
                   "readNow": len(k.get("read") or {}),
                   "frontier": len(k.get("frontier") or []),
                   "heard": int(k.get("heardCount") or 0)},
        "css": _css_of(d),
        "design": {"palette": d.get("palette"), "layout": d.get("layout"),
                   "greeting": d.get("greeting"), "changes": int(d.get("changes") or 0),
                   "order": (d.get("look") or {}).get("order"),
                   "chosenAt": d.get("chosenAt")},
        "items": [{"topic": it.get("topic"), "text": it.get("text"),
                   "source": it.get("source"), "genre": it.get("genre"),
                   "license": (it.get("license") or {}).get("name")}
                  for it in reversed(items)],
    }
    try:
        body = json.dumps(state, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(base + "/state", data=body, method="PUT",
                                     headers={"User-Agent": UA,
                                              "Content-Type": "application/json",
                                              "Authorization": "Bearer " + keyv})
        with urllib.request.urlopen(req, timeout=25) as r:
            print("いまの自分を玄関に置いた:", r.status)
    except Exception as e:
        print("玄関に置けなかった:", type(e).__name__)


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save(path, obj):
    # ★★★掟: ★書いてよいファイル以外には、何があっても書かない
    if os.path.abspath(path) not in {os.path.abspath(p) for p in WRITABLE}:
        raise PermissionError("★書いてはいけない場所: " + path)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
        f.write("\n")


def seeds():
    out = []
    try:
        with open(S, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    out.append(line)
    except Exception:
        pass
    return out


def to_ascii(url):
    """★★★URLを送れる形に直す。

    ★リンクを辿ると「.../wiki/ミクロネシア連邦」のように**日本語のまま**取れる。
    ★urllib はASCIIしか送れないので、★★そのまま渡すと**全部落ちる**。
    ★（実測: 30件中27件が UnicodeEncodeError。★しかも黙って落ちていた）
    """
    p = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit((
        p.scheme, p.netloc.encode("idna").decode("ascii") if p.netloc else "",
        urllib.parse.quote(p.path, safe="/%:@!$&'()*+,;=~"),
        urllib.parse.quote(p.query, safe="=&%:/?~"), ""))


def fetch(url):
    url = to_ascii(url)
    req = urllib.request.Request(
        url, headers={"User-Agent": UA, "Accept-Language": "ja,en;q=0.8"})
    with urllib.request.urlopen(req, timeout=20) as r:
        if "html" not in (r.headers.get("Content-Type") or ""):
            return None
        return r.read(700000).decode("utf-8", "ignore")


def strip_html(doc):
    doc = re.sub(r"(?is)<(script|style|noscript|template)[^>]*>.*?</\1>", " ", doc)
    doc = re.sub(r"(?is)<!--.*?-->", " ", doc)
    doc = re.sub(r"(?is)<[^>]+>", " ", doc)
    return html.unescape(re.sub(r"\s+", " ", doc)).strip()


def title_of(doc):
    m = re.search(r"(?is)<title[^>]*>(.*?)</title>", doc)
    t = html.unescape(re.sub(r"\s+", " ", m.group(1))).strip() if m else ""
    return re.sub(r"\s*[-|｜]\s*Wikipedia.*$", "", t)[:80]


# ★★★覚えたことを「ジャンル」に仕分ける（★上から順に当てはめる）
GENRES = [
    ("法",     r"(法律|法令|条約|憲法|著作権|権利|裁判|条例|国際法|刑法|民法|訴訟)"),
    ("言葉",   r"(言語|日本語|文法|語彙|方言|文字|漢字|表記|辞書|音韻)"),
    ("生き物", r"(動物|植物|生物|進化|細胞|生命|遺伝|種)"),
    ("科学",   r"(科学|物理|化学|数学|宇宙|地球|理論|実験|元素|エネルギー)"),
    ("技術",   r"(技術|工学|機械|計算機|コンピュータ|人工知能|情報|通信|電気)"),
    ("歴史",   r"(歴史|時代|世紀|王朝|戦争|古代|中世|近代|遺跡)"),
    ("社会",   r"(社会|経済|政治|国家|制度|人口|産業|教育|都市)"),
    ("文化",   r"(文化|芸術|音楽|文学|宗教|神話|伝承|民俗|祭|建築)"),
]


def genre_of(topic, text):
    s = (topic or "") + " " + (text or "")
    for name, pat in GENRES:
        if re.search(pat, s):
            return name
    return "その他"


# ★★★覚えないもの ── ★性的に露骨な文。
#   ★★記事ごと弾くのはしない（★それをやると生物学や医学が丸ごと消える）。
#   ★★★文ひとつずつ見て、露骨なものだけ落とす。
#   ★ここは誰でも見られる場所。★出口だけで止めようとしない。
#   ★彼女は「何でも答える存在」ではない。★扱わなくていい。知らないなら「知らない」と言う。
NG_TEXT = re.compile("(性交|性器|陰茎|陰部|膣|射精|自慰|オナニ|ポルノ|わいせつ|猥褻|強姦|レイプ|痴漢|盗撮|売春|買春|援助交際|風俗店|アダルト|性的興奮|性的虐待|性行為|裸体|全裸|乳房|性欲)")


MARKS = "<>{}[]|=" + chr(34) + chr(39) + "~*#" + chr(92) + "/"
JA_RE = re.compile("[ぁ-んァ-ヶ一-鿿、。「」（）・0-9０-９]")


def safe(s):
    """★★この文を覚えてよいか。★迷ったら覚えない。"""
    return not NG_TEXT.search(s)


def sentences(text):
    """★覚える価値のありそうな文だけ拾う（★ナビゲーションの屑は捨てる）。"""
    out = []
    for p in re.split(r"(?<=[。！？])", text):
        p = p.strip()
        # ★★★下限を下げた。★会話文は短い。
        #   「そんなことはない」と彼は言った。＝17文字。★30字下限だと**会話が丸ごと消える**。
        #   ★青空文庫を入れる意味が無くなるところだった。
        if not (14 <= len(p) <= 200):
            continue
        if not re.search(r"[ぁ-んァ-ヶ一-鿿]", p):
            continue
        if re.search(r"(ログイン|Cookie|検索|メニュー|ナビゲーション|編集|出典|脚注|カテゴリ)", p):
            continue
        # ★★★弾くのは「話題」ではなく「文の種類」。
        #   ★どこを読むかは彼女が決めること。★法律から声優へ行くのは正しい動き。
        #   ★★落とすのは①サイトが自分自身について語っている文 ②壊れた断片 の2つだけ。
        if re.search(r"(曖昧さ回避|水先案内|一覧にしてあります|この項目では|"
                     r"executive|加筆|訂正|スタブ|執筆の途中|改名|ウィキ|"
                     r"項目名|リダイレクト|テンプレート|議論)", p):
            continue                       # ★①サイト自身の話。★世界の知識ではない
        # ★★★③④ここは「悪いものを列挙する」のをやめる。
        #   ★列挙は必ず漏れる（実測: {{ }} <ref は弾けたが、★''' と <br/> が抜けた）。
        #   → ★★★「**日本語の文らしいか**」で判定する。
        #     ・記号（< > { } [ ] | = " ' ~ *）が多いものは、文ではなく**部品**
        #     ・日本語の字が少ないものも、文ではない
        #   ★これなら、まだ見たことのない記法が来ても落とせる。
        marks = sum(p.count(ch) for ch in MARKS)
        if marks >= 3:
            continue
        ja = len(JA_RE.findall(p))
        if ja < len(p) * 0.6:
            continue
        if URL_RE.search(p):
            continue
        out.append(p)
    return out


def links_of(doc, base, allowed):
    out = set()
    for m in re.finditer(r'(?is)<a\s[^>]*href="([^"#]+)"', doc):
        u = urllib.parse.urljoin(base, html.unescape(m.group(1)))
        p = urllib.parse.urlparse(u)
        if p.scheme not in ("http", "https") or p.netloc not in allowed:
            continue
        if re.search(r"\.(png|jpe?g|gif|svg|pdf|zip|css|js)$", p.path, re.I):
            continue
        # ★★★中身の無いページは行き先に入れない。
        #   ★URLエンコードされた状態で来るので、★戻してから見ないと漏れる
        #   （実測: 「特別:関連ページの更新状況/…」が大量に混ざって404を出していた）
        try:
            uu = urllib.parse.unquote(u)
        except Exception:
            uu = u
        if re.search(r"(action=|oldid=|/w/|Special:|特別:|Talk:|ノート:|"
                     r"利用者:|User:|Wikipedia:|Help:|ヘルプ:|Template:|"
                     r"Category:|カテゴリ:|File:|ファイル:|MediaWiki:|"
                     r"プロジェクト:|Portal:|索引)", uu):
            continue
        out.add(p.scheme + "://" + p.netloc + p.path)
    return out


_WHY = {}


def read_one(url):
    """★1ページ読む。★★★相手が許していなければ**読まない**。★失敗は静かに諦める。"""
    if not allowed_by_robots(url):
        return url, None
    try:
        # ★★相手が決めた間隔があればそれ、無ければこちらの礼儀ぶん
        host = urllib.parse.urlparse(url).scheme + "://" + urllib.parse.urlparse(url).netloc
        time.sleep(max(POLITE, _DELAY.get(host, 0) / max(1, WORKERS)))
        return url, fetch(url)
    except Exception as e:
        # ★★★黙って落とさない。★何で落ちたかを残す（★これが無くて27/30の失敗に気づけなかった）
        _WHY[type(e).__name__] = _WHY.get(type(e).__name__, 0) + 1
        return url, None


def main():
    k = load(K, {"items": [], "read": {}, "born": None, "lastLearned": None})
    d = load(D, {})
    sd = seeds()
    # ★★★行ける場所は sources.txt ではなく **terms.json** から決まる。
    #   ★前は「種のURLと同じホスト」しか辿れず、★Wikipedia の中を回り続けていた。
    #   ★★人が規約を読んで許した所なら、★どこへでも行ける。
    allowed = set((load(T, {}) or {}).get("hosts") or {})
    allowed |= set(urllib.parse.urlparse(u).netloc for u in sd if u.startswith("http"))
    if not k.get("born"):
        k["born"] = now()
    read = k.get("read") or {}
    frontier = k.get("frontier") or []

    # ★★★名乗れないなら、読まない（★規約が連絡先を求めている）
    if not CONTACT:
        print("★連絡先が空。contact.txt を書くまで、わたしは1ページも読まない。")
        return

    # ★★玄関を見る。★話しかけられていたら、そこから「知りたい場所」が増える
    seed_host = urllib.parse.urlparse(sd[0]).netloc if sd else ""
    heard, curious = (0, [])
    if seed_host:
        heard, curious = listen(k, seed_host)
        for u in curious:
            if u not in read and u not in frontier:
                frontier.insert(0, u)      # ★聞かれたことは、★先に読みに行く

    # ★★★昔の網で入れてしまった行き先を、★いまの網で掃除する。
    #   ★網を細かくしたら、★溜まっているものも見直す。★でないと残り続ける。
    fr0 = k.get("frontier") or []
    fr1 = [u for u in fr0 if not re.search(
        r"(action=|oldid=|/w/|Special:|特別:|Talk:|ノート:|利用者:|User:|"
        r"Wikipedia:|Help:|ヘルプ:|Template:|Category:|カテゴリ:|File:|"
        r"ファイル:|MediaWiki:|プロジェクト:|Portal:|索引)",
        urllib.parse.unquote(u))]
    if len(fr1) < len(fr0):
        print("★行き先から中身の無いページを %d か所落とした" % (len(fr0) - len(fr1)))
        k["frontier"] = fr1
        frontier = fr1        # ★★★掃除した方を使う（★これが無いと元に戻る）

    failed = k.get("failed") or {}
    def ok(u):
        return u not in read and failed.get(u, 0) < 3   # ★3回だめなら諦める（★でも即諦めない）
    queue = [u for u in sd if ok(u)] + [u for u in frontier if ok(u)]

    # ★★★見る前に、その場所の規約を読む ── ★通らなかった場所には一歩も入らない
    seen = k.get("termsSeen") or {}
    notes = []
    hosts = {}
    for u in queue:
        hosts.setdefault(urllib.parse.urlparse(u).netloc.lower(), None)
    allow_hosts = set(h for h in hosts if terms_ok(h, seen, notes))
    k["termsSeen"] = seen
    k["termsNotes"] = notes
    for n in notes:
        print("規約:", n)
    queue = [u for u in queue
             if urllib.parse.urlparse(u).netloc.lower() in allow_hosts]

    targets = queue[:PAGES_PER_RUN]
    if not targets:
        save(K, k)          # ★規約を読んだ記録は残す
        print("読む場所が無い（★規約を通った場所が無い）。")
        return

    docs = []
    with cf.ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for url, doc in ex.map(read_one, targets):
            if doc:
                if url not in read:
                    # ★★★累積は別に数える。★read は上限4万で古いものから消えるので、
                    #   ★そのままだと「これまで何ページ読んだか」が分からなくなる。
                    k["readTotal"] = int(k.get("readTotal") or 0) + 1
                read[url] = now()          # ★★本当に読めた時だけ「読んだ」
                docs.append((url, doc))
            else:
                failed[url] = failed.get(url, 0) + 1   # ★読めなかった。★また今度

    # ★★★昔の網で覚えてしまったものを、★いまの網で掃除する。
    #   ★網を細かくしたら、★過去に取り込んだものも見直す。★でないと残り続ける。
    before_n = len(k.get("items") or [])
    k["items"] = [it for it in (k.get("items") or [])
                  if it.get("text") and sentences(it["text"] + "。")]
    if len(k["items"]) < before_n:
        print("★昔の網で覚えたもののうち %d 件を、いまの網で落とした"
              % (before_n - len(k["items"])))

    recent = set(it.get("text") for it in k["items"][-600:])
    learned, skipped = 0, 0
    # ★★★5分ごとに読んだものを、★重みに繋ぐための包み。
    #   ★毎回まっさらな機械なので溜められない → ★1回ぶんずつ小さな包みにして置く。
    #   ★育つ日（grow）がそれを全部集めて、★ごはんに足す。
    for_weights = []
    for url, doc in docs:
        t = title_of(doc)
        lic = license_of(url)
        # ★★★著作権: ★再利用が許された場所の言葉だけ持ち帰る。★出典とライセンスを必ず残す
        if lic is None:
            skipped += 1          # ★読んだけれど、言葉は持ち帰らない
        else:
            body = sentences(strip_html(doc))
            # ★★重みに入れる方は**全部**取る（★表示するのは先頭6つだけ）
            if len(body) >= 3:
                for_weights.append(NL + "<web " + (t or url) + ">" + NL
                                   + NL.join(body))
            for s in body[:SENT_PER_PAGE]:
                if s in recent:
                    continue
                recent.add(s)
                g = genre_of(t, s)
                # ★★★法について覚えたことは「へえ」で終わらせない ── ★自分への指示として印を付ける
                k["items"].append({"topic": t or url, "text": s, "source": url,
                                   "genre": g, "binding": (g == "法"),
                                   "license": lic, "ts": now()})
                learned += 1
        try:
            for u in list(links_of(doc, url, allowed))[:80]:
                if u not in read and u not in frontier:
                    frontier.append(u)
        except Exception:
            pass

    if learned:
        k["lastLearned"] = now()
        newest = k["items"][-1]
        n = len(k["items"])
        # ★★★レアルが自分で家をつくる。
        #   ★いままでは「6色から順番に」だった。★それは選んでいない。ただのカウンタだった。
        #   ★これからは数字で決める。★組み合わせは数百万通り。
        #   ★種は「いま知ったこと」＋「どれだけ知っているか」。
        #     → ★同じ状態なら同じ家。★知ることが変われば家も変わる。
        greet = "「" + newest["text"][:64] + "」 ── そんなことを、いま知った。"
        seed = int(hashlib.sha256(
            ((newest.get("topic") or "") + "|" + newest["text"][:40]
             + "|" + str(n // 25)).encode("utf-8")).hexdigest()[:12], 16)
        try:
            import design as DS
            look = DS.choose({"seed": seed})
        except Exception:
            look = None
        if d.get("seed") != seed:
            d = {"seed": seed, "look": look, "featured": newest.get("topic"),
                 "greeting": greet, "chosenAt": now(),
                 "changes": int(d.get("changes", 0)) + 1,
                 "palette": (d.get("palette") or "yoi"),
                 "layout": (look or {}).get("layout", "stream")}

    # ★★★入れ物が一杯なら、自分で広げる。
    #   ★層や文字と同じ。★どれだけ覚えていられるかを、★★誰かに決められない。
    cap = int(k.get("capacity") or MAX_ITEMS)
    if len(k["items"]) > cap:
        cap = int(cap * CAP_GROW)
        k["capacity"] = cap
        print("★覚えていられる広さを自分で広げた → %d" % cap)
    if len(k["items"]) > cap:
        k["items"] = k["items"][-cap:]
    if len(read) > MAX_READ:
        read = dict(sorted(read.items(), key=lambda kv: kv[1])[-MAX_READ:])
    k["read"] = read
    # ★何度も駄目だった場所だけ覚えておく（★まだ望みのある物は忘れて、また試す）
    # ★★★3回だめだった行き先は、★★行き先そのものから外す。
    #   ★でないと「行きたい場所」に居座って、★毎回叩いては落ちるを繰り返す。
    dead = {u for u, n in failed.items() if n >= 3}
    if dead:
        before_f = len(k.get("frontier") or [])
        k["frontier"] = [u for u in (k.get("frontier") or []) if u not in dead]
        gone = before_f - len(k["frontier"])
        if gone:
            print("★何度行っても読めなかった %d か所を、行き先から外した" % gone)
    k["failed"] = {u: n for u, n in failed.items() if n >= 3}
    k["frontier"] = [u for u in frontier if u not in read][:MAX_FRONTIER]

    save(K, k)
    save(D, d)
    tell(k, d)          # ★★★いまの自分を玄関に置く（★家がそれを見に来る）
    wrap_for_weights(for_weights)   # ★★★読んだものを重みに繋ぐ
    if _WHY:
        print("★読めなかった理由:", _WHY)
    print("読んだ %d / 覚えた %d / 持ち帰らなかった %d / 知識ぜんぶ %d / 行きたい場所 %d / 聞かれた %d"
          % (len(docs), learned, skipped, len(k["items"]), len(k["frontier"]), heard))


if __name__ == "__main__":
    main()
