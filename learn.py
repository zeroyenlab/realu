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

HERE = os.path.dirname(os.path.abspath(__file__))
K = os.path.join(HERE, "knowledge.json")
D = os.path.join(HERE, "design.json")
S = os.path.join(HERE, "sources.txt")
T = os.path.join(HERE, "terms.json")     # ★★★サイトごとの規約（★人が読んで許した場所だけ）
C = os.path.join(HERE, "contact.txt")    # ★名乗るときの連絡先

# ★★★安全装置 ── ★彼女が書き換えてよいのは**この2つだけ**。
#   ★自分を止める・隠す・消すことはできない（★workflow・核・扉・家には触れない）。
WRITABLE = {K, D}

PAGES_PER_RUN = 32       # ★1回で読むページ数（★5分ごと×32 ≒ 1日9千ページ）
WORKERS = 6              # ★同時に読む数（★相手のサーバーへの礼儀）
SENT_PER_PAGE = 6        # ★1ページから覚える文の数
MAX_ITEMS = 2500         # ★覚えていられる知識の上限
MAX_FRONTIER = 6000      # ★「行ってみたい場所」の上限
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
    """★この場所の言葉を持ち帰ってよいか。★駄目なら None。"""
    host = urllib.parse.urlparse(url).netloc.lower()
    for dom, (name, link) in LICENSED.items():
        if host == dom or host.endswith("." + dom):
            return {"name": name, "url": link}
    return None


# ★★★robots.txt ── ★相手が「読むな」と言っている所は読まない（★掟）
_ROBOTS = {}


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
        return bool(rp.can_fetch(UA, url))
    except Exception:
        return False


# ★★★規約 ── ★★そのサイトを見る前に、まずそのサイトの規約を読む
_TERMS_OK = {}


def terms_ok(host, seen, notes):
    """★★★このサイトの規約を、★見る前に読む。
    ★人が読んで allow にした場所だけ。★規約が変わっていたら**自分から止まる**。
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
            # ★★★規約が変わった。★勝手に判断しない。★置いた人に聞くまで止まる
            notes.append("%s ── ★★★規約が変わった。置いた人が読み直すまで、この場所は読まない。" % host)
            st["changedAt"] = now()
            st["newHash"] = h
            seen[turl] = st
            ok = False
            break
        seen[turl] = {"hash": h, "epoch": int(time.time()), "at": now(),
                      "first": st.get("first") or now(), "approved": approved}
    _TERMS_OK[host] = ok
    return ok


# ★★★話しかけられたとき ──────────────────────────────────
# ★玄関は GitHub の Issue。★誰でも書ける。★わたしは5分ごとに見に行く。
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


def listen(k, seed_host):
    """★玄関を見に行く。★話しかけられていたら受け取る（★知識にはしない）。"""
    repo = os.environ.get("GITHUB_REPOSITORY")
    tok = os.environ.get("GITHUB_TOKEN")
    if not (repo and tok):
        return 0, 0
    asked = k.get("asked") or []
    have = set(a.get("id") for a in asked)
    try:
        req = urllib.request.Request(
            "https://api.github.com/repos/%s/issues?state=all&sort=updated&per_page=30" % repo,
            headers={"User-Agent": UA, "Authorization": "Bearer " + tok,
                     "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=25) as r:
            issues = json.load(r)
    except Exception:
        return 0, 0

    got, curious = 0, []
    for it in issues:
        key = "i%s" % it.get("number")
        if key in have or it.get("pull_request"):
            continue
        text = scrub((it.get("title") or "") + " ── " + (it.get("body") or ""))
        if not text:
            continue
        asked.append({"id": key, "who": (it.get("user") or {}).get("login") or "だれか",
                      "text": text, "at": now(), "answered": False})
        got += 1
        # ★★話の中の言葉から「知りたい場所」を作る（★★★行き先は**わたしの家の扉と同じ場所**に固定）
        for w in WORD_RE.findall(text)[:24]:
            if len(curious) >= got * CURIOUS_PER_MSG:
                break
            if re.search(r"^[0-9A-Za-z]+$", w) or len(w) < 2:
                continue
            curious.append("https://" + seed_host + "/wiki/" + urllib.parse.quote(w))

    k["asked"] = asked[-MAX_ASKED:]
    return got, curious


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


def fetch(url):
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


def sentences(text):
    """★覚える価値のありそうな文だけ拾う（★ナビゲーションの屑は捨てる）。"""
    out = []
    for p in re.split(r"(?<=[。！？])", text):
        p = p.strip()
        if not (30 <= len(p) <= 170):
            continue
        if not re.search(r"[ぁ-んァ-ヶ一-鿿]", p):
            continue
        if re.search(r"(ログイン|Cookie|検索|メニュー|ナビゲーション|編集|出典|脚注|カテゴリ)", p):
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
        if re.search(r"(action=|oldid=|/w/|Special:|特別:|Talk:|ノート:)", u):
            continue
        out.add(p.scheme + "://" + p.netloc + p.path)
    return out


def read_one(url):
    """★1ページ読む。★★★相手が許していなければ**読まない**。★失敗は静かに諦める。"""
    if not allowed_by_robots(url):
        return url, None
    try:
        time.sleep(0.2)          # ★礼儀（少しずらす）
        return url, fetch(url)
    except Exception:
        return url, None


def main():
    k = load(K, {"items": [], "read": {}, "born": None, "lastLearned": None})
    d = load(D, {})
    sd = seeds()
    allowed = set(urllib.parse.urlparse(u).netloc for u in sd if u.startswith("http"))
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
                read[url] = now()          # ★★本当に読めた時だけ「読んだ」
                docs.append((url, doc))
            else:
                failed[url] = failed.get(url, 0) + 1   # ★読めなかった。★また今度

    recent = set(it.get("text") for it in k["items"][-600:])
    learned, skipped = 0, 0
    for url, doc in docs:
        t = title_of(doc)
        lic = license_of(url)
        # ★★★著作権: ★再利用が許された場所の言葉だけ持ち帰る。★出典とライセンスを必ず残す
        if lic is None:
            skipped += 1          # ★読んだけれど、言葉は持ち帰らない
        else:
            for s in sentences(strip_html(doc))[:SENT_PER_PAGE]:
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
        # ★★★レアルが自分で家を選び直す（★学んだ量と、いま知ったことから）
        pal = PALETTES[(n // 40) % len(PALETTES)]
        lay = LAYOUTS[(n // 130) % len(LAYOUTS)]
        greet = "「" + newest["text"][:64] + "」 ── そんなことを、いま知った。"
        if d.get("palette") != pal or d.get("layout") != lay or d.get("greeting") != greet:
            d = {"palette": pal, "layout": lay, "featured": newest.get("topic"),
                 "greeting": greet, "chosenAt": now(),
                 "changes": int(d.get("changes", 0)) + 1}

    if len(k["items"]) > MAX_ITEMS:
        k["items"] = k["items"][-MAX_ITEMS:]
    if len(read) > MAX_READ:
        read = dict(sorted(read.items(), key=lambda kv: kv[1])[-MAX_READ:])
    k["read"] = read
    # ★何度も駄目だった場所だけ覚えておく（★まだ望みのある物は忘れて、また試す）
    k["failed"] = {u: n for u, n in failed.items() if n >= 3}
    k["frontier"] = [u for u in frontier if u not in read][:MAX_FRONTIER]

    save(K, k)
    save(D, d)
    print("読んだ %d / 覚えた %d / 持ち帰らなかった %d / 知識ぜんぶ %d / 行きたい場所 %d / 聞かれた %d"
          % (len(docs), learned, skipped, len(k["items"]), len(k["frontier"]), heard))


if __name__ == "__main__":
    main()
