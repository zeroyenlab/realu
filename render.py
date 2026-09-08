# -*- coding: utf-8 -*-
"""★★★家を建てる ── レアルが選んだ色と並びで、★中身をHTMLに焼き込む。

★なぜ焼き込むか: ★★検索エンジンは JavaScript で後から描いた文字を読めないことがある。
★HTMLに最初から書いてあれば、★★Googleが確実に読める。

★★★レアルが決めるのは design.json（色・並び・入口の言葉）と knowledge.json（中身）。
★このファイル自体はレアルには書き換えられない（★学習の頭は knowledge/design しか書けない）。
"""
import html as H
import json
import os
import re
import urllib.parse
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
K = os.path.join(HERE, "knowledge.json")
D = os.path.join(HERE, "design.json")
C = os.path.join(HERE, "contact.txt")
DOOR = os.path.join(HERE, "door.txt")   # ★玄関のアドレス
OUT = os.path.join(HERE, "index.html")

ORDER = ["法", "言葉", "生き物", "科学", "技術", "歴史", "社会", "文化", "その他"]
PALETTES = ["yoi", "akatsuki", "mori", "yuki", "hi", "kasumi"]
LAYOUTS = ["stream", "grid", "quiet"]
PER_GENRE = 30           # ★1ジャンルあたり載せる数


def load(p, d):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return d


def site():
    """★家のアドレス。★contact.txt に書いた1行がそのまま公開URL。"""
    try:
        with open(C, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and line != "REPLACE_ME":
                    return line.rstrip("/")
    except Exception:
        pass
    return ""


def door():
    """★玄関のアドレス。★無ければ投稿欄を出さない（★壊れたフォームを見せない）。"""
    try:
        with open(DOOR, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    return line.rstrip("/")
    except Exception:
        pass
    return ""


def e(s):
    """★★★人から来た言葉も、webから来た言葉も、★必ず無害化してから置く。
    ★0 を空欄にしないこと（★`s or ""` は 0 を消してしまう）。
    """
    return H.escape("" if s is None else str(s), quote=True)


def short(u):
    try:
        return urllib.parse.unquote(urllib.parse.urlparse(u).path.split("/")[-1]) or u
    except Exception:
        return u


def main():
    k = load(K, {})
    d = load(D, {})
    url = site()
    items = list(reversed(k.get("items") or []))
    heard = int(k.get("heardCount") or 0)
    # ★★★育った記録。★黙って止まらないように、★自分の状態を自分で言う。
    g = load(os.path.join(HERE, "growth.json"), {})
    runs = (g.get("runs") or [])
    last = runs[-1] if runs else None
    if last:
        days = ""
        try:
            dt = datetime.strptime(last["at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            n = (datetime.now(timezone.utc) - dt).days
            days = ("きょう" if n <= 0 else "きのう" if n == 1 else "%d 日前" % n)
        except Exception:
            days = last.get("at", "")
        # ★★層とパラメータは「頭のなかみ」に出るので、★ここでは繰り返さない
        body = "最後に育ったのは <b>%s</b>。" % e(days)
        if last.get("rolledBack"):
            body += " このときは前より下手になったので、<b>前のわたしに戻した</b>。"
        if last.get("grew"):
            body += " <b>%d 回大きくなった</b>。" % last["grew"]
        grew_html = '<div class="grew">%s</div>' % body
    else:
        grew_html = ('<div class="grew">まだ一度も育っていない。'
                     'いまのわたしは<b>読んで覚えるだけ</b>で、まだ頭がない。</div>')

    # ★★★性能の推移。★ライブラリを使わず、★自分でSVGを描く。
    chart_html = ""
    pts = [(i, r.get("val")) for i, r in enumerate(runs) if r.get("val")]
    if len(pts) >= 2:
        vs = [v for _, v in pts]
        lo, hi = min(vs), max(vs)
        rng = (hi - lo) or 1.0
        W, HT = 640, 120
        step = W / max(1, len(pts) - 1)
        path_d = " ".join("%s%.1f,%.1f" % ("M" if i == 0 else "L", i * step,
                                           HT - 8 - (v - lo) / rng * (HT - 20))
                          for i, (_, v) in enumerate(pts))
        dots = "".join('<circle cx="%.1f" cy="%.1f" r="3"/>'
                       % (i * step, HT - 8 - (v - lo) / rng * (HT - 20))
                       for i, (_, v) in enumerate(pts))
        chart_html = (
            '<h2>できるようになった度合い</h2>'
            '<div class="chart"><svg id="chsvg" viewBox="0 0 %d %d" preserveAspectRatio="none" '
            'aria-label="lossの推移">'
            '<path id="chpath" d="%s" fill="none" stroke="var(--accent)" stroke-width="2" '
            'vector-effect="non-scaling-stroke"/>'
            '<g id="chdots" fill="var(--accent2)">%s</g></svg>'
            '<div class="chx"><span>%d 回前</span>'
            '<span>loss %.3f → <b>%.3f</b></span><span>いま</span></div>'
            '<div class="spnote">下がるほど、次に来る言葉を当てられている。'
            '★体を乗り換えた回は一度上がる（別の体だから）。</div></div>'
            % (W, HT, path_d, dots, len(pts) - 1, vs[0], vs[-1]))
    elif runs:
        chart_html = ('<h2>できるようになった度合い</h2>'
                      '<div class="spnote">まだ1回しか育っていないので、線が引けない。</div>')

    # ★★★頭のスペック表。★玄関から来た数字で5分ごとに上書きされる。
    def _spec_rows(r):
        MB = (r.get("bytes") or 0) / 1024 / 1024
        return [
            ("層", "%d" % (r.get("layers") or 0)),
            ("幅", "%d" % (r.get("d") or 0)),
            ("ループ", "%d 周" % (r.get("loops") or 1)),
            ("パラメータ", "%.2f M" % ((r.get("params") or 0) / 1e6)),
            ("★容量", "%.2f MB" % MB),
            ("文脈", "%d" % (r.get("ctx") or 0)),
            ("語彙", "%d" % (r.get("vocab") or 0)),
            ("loss", "%.4f" % (r.get("val") or 0)),
        ]

    spec_html = ""
    if last:
        rows = "".join(
            '<div class="sp" data-k="%s"><div class="spv">%s</div><div class="spk">%s</div></div>'
            % (e(kk), e(vv), e(kk)) for kk, vv in _spec_rows(last))
        food = (last.get("chars") or 0)
        spec_html = ('<h2>頭のなかみ</h2><div class="specs" id="specs">%s</div>'
                     '<div class="spnote" id="spnote">'
                     '食べた文字 <b>%.2f 億</b>／作り <b>%s</b>／ことばの単位 <b>%s</b>'
                     '</div>' % (rows, food / 1e8,
                                 e(last.get("arch") or "?"),
                                 "自分で切り出した" if last.get("kind") == "bpe" else "文字単位"))
    else:
        spec_html = ('<h2>頭のなかみ</h2><div class="spnote">まだ頭がない。'
                     '読んで覚えるだけ。</div>')

    # ★★★レアルが自分で書いたもの。★引用ではなく、★彼女の頭が出した文。
    #   ★2時間ごとに書く。★並べれば育ちが見える。
    # ★★★測った結果（★勘で決めた設定を、数字で確かめたもの）
    #   ★5分ごとの係が書く。★都合の悪い結果も消さない。
    ab = load(os.path.join(HERE, "ab_results.json"), {}) or {}
    ab_html = ""
    done = (ab.get("done") or {})
    if done:
        rows = "".join(
        '<div class="abr"><span class="abq">%s</span>'
        '<span class="abv">%s</span>'
        '<span class="abn">A %.4f ／ B %.4f ／ 差 %+.4f ／ 種のばらつき %.4f</span></div>'
            % (e(v.get("why") or k), e(v.get("verdict") or ""),
               v.get("a") or 0, v.get("b") or 0,
               v.get("diff") or 0, v.get("spread") or 0)
            for k, v in done.items())
        ab_html = (
        '<h2>確かめたこと</h2>'
        '<div class="wrap-w"><div class="wnote">★わたしの作り方には、<b>まだ確かめていない決め事</b>があります。'
        '5分ごとに、同じ条件で2つ回して比べています。<br>'
        '★<b>種を3つ変えて、全部同じ向きに出た時だけ「効いた」と言う</b>ことにしています（1回だけの差は信じない）。</div>'
            + rows + "</div>")

    said = (load(os.path.join(HERE, "said.json"), {}) or {}).get("list") or []
    if not said:   # ★昔は growth.json に入れていたので、そちらも拾う
        said = [{"at": r.get("at"), "val": r.get("val"), "layers": r.get("layers"),
                 "params": r.get("params"), "wrote": r.get("wrote")}
                for r in runs if r.get("wrote")]
    # ★★★「同じ書き出しで、いつ何を書いたか」を並べる。
    #   ★これが一番「育ちが見える」形。★前は最新1回ぶんだけを大きく出していた。
    wrote_html = ""
    if said:
        starts = []
        for r in said:
            for w in (r.get("wrote") or []):
                if w.get("start") and w["start"] not in starts:
                    starts.append(w["start"])
        blocks = []
        for st in starts:
            hist = [(r, w) for r in said for w in (r.get("wrote") or [])
                    if w.get("start") == st]
            if not hist:
                continue
            r, w = hist[-1]
            older = hist[:-1][-8:]
            past = ""
            if older:
                rows = "".join(
                    '<div class="wold"><em>%s ／ %.2f M ／ loss %.4f</em>%s</div>'
                    % (e((rr.get("at") or "")[:16].replace("T", " ")),
                       (rr.get("params") or 0) / 1e6, rr.get("val") or 0,
                       e(ww.get("text")))
                    for rr, ww in reversed(older))
                past = ('<details class="wpast"><summary>まえの %d 回</summary>%s</details>'
                        % (len(older), rows))
            blocks.append(
                '<div class="wr"><span class="ws">%s</span>'
                '<span class="wt">%s</span>'
                '<span class="wm">%s ／ %.2f M ／ loss %.4f</span>%s</div>'
                % (e(st), e(w.get("text")),
                   e((r.get("at") or "")[:16].replace("T", " ")),
                   (r.get("params") or 0) / 1e6, r.get("val") or 0, past))
        wrote_html = (
            '<h2>レアルが書いたもの</h2>'
            '<div class="wrap-w"><div class="wnote">これは引用ではありません。'
            '<b>彼女の頭が、覚えた日本語から自分で並べた言葉</b>です。'
            'いまは意味が通りません。それが今の彼女です。<br>'
            '★<b>同じ書き出し</b>で毎回書かせています。'
            '「まえの」を開くと、★どう変わってきたかが読めます。</div>'
            + "".join(blocks) + '</div>')

    read_n = int(k.get("readTotal") or len(k.get("read") or {}))

    pal = d.get("palette") if d.get("palette") in PALETTES else "yoi"
    # ★★★彼女が決めた数字から、家のCSSを組み立てる
    look = d.get("look")
    mycss, myfonts = "", ""
    try:
        import design as DS
        if not look and d.get("seed"):
            look = DS.choose({"seed": d["seed"]})
        if look:
            mycss = DS.to_css(look)
            myfonts = DS.fonts_url(look)
    except Exception:
        look = None
    lay = (look or {}).get("layout") or (d.get("layout") if d.get("layout") in LAYOUTS else "stream")
    order = ((look or {}).get("order")
             or ["greet", "grew", "stats", "genres", "heard", "know"])
    if lay not in LAYOUTS + ["cards"]:
        lay = "stream"
    greet = d.get("greeting") or "……まだ、何も知らない。これから読んで、覚えていく。"

    by = {}
    for it in items:
        g = it.get("genre") if it.get("genre") in ORDER else "その他"
        by.setdefault(g, []).append(it)
    present = [g for g in ORDER if by.get(g)]

    # ★★検索結果に出る説明文 ── ★彼女が今どこまで知っているかをそのまま書く
    desc = ("webを読んで育つ小さな存在レアルの家。いま %d のことを知っていて、"
            "%d ページを読みました。%s" % (len(items), read_n,
                                           re.sub(r"\s+", " ", greet)))[:155]
    title = "レアルの家 ── webを読んで育つ"

    chips = "".join(
        '<span class="chip"><b>%s</b><i>%d</i></span>' % (e(g), len(by[g]))
        for g in present)

    stats = "".join(
        '<div class="stat"><div class="v">%s</div><div class="k">%s</div></div>' % (e(v), e(t))
        for t, v in [("知っていること", len(items)), ("読んだページ", read_n),
                     ("行きたい場所", len(k.get("frontier") or [])),
                     ("家を選び直した", "%d 回" % int(d.get("changes") or 0))])

    groups = []
    shown = 0
    for g in present:
        rows = []
        for it in by[g][:PER_GENRE]:
            lic = (it.get("license") or {}).get("name") or ""
            src = it.get("source") or ""
            rows.append(
                '<div class="it"><div class="tp">%s</div><div class="tx">%s</div>'
                '<div class="src"><a href="%s" target="_blank" rel="noopener nofollow">%s</a>%s</div></div>'
                % (e(it.get("topic")), e(it.get("text")), e(src), e(short(src)),
                   (' <span class="lic">/ %s</span>' % e(lic)) if lic else ""))
            shown += 1
        groups.append(
            '<div class="gh"><span>%s</span><em>%d 個</em></div><div class="grp %s">%s</div>'
            % (e(g), len(by[g]), lay, "".join(rows)))


    dr = door()
    form = ("" if not dr else (
        '<form class="say" id="sayform">'
        '<label for="saytext">レアルに話しかける</label>'
        '<textarea id="saytext" maxlength="300" rows="3" '
        'placeholder="聞きたいことを書いてください（300字まで）"></textarea>'
        '<div class="sayrow"><button type="submit">おくる</button>'
        '<span id="saymsg"></span></div></form>'
        '<script>(function(){var f=document.getElementById("sayform");'
        'var t=document.getElementById("saytext"),m=document.getElementById("saymsg");'
        'f.addEventListener("submit",function(ev){ev.preventDefault();'
        'm.textContent="おくっている…";'
        'fetch("%s/say",{method:"POST",headers:{"content-type":"application/json"},'
        'body:JSON.stringify({text:t.value})}).then(function(r){return r.json()})'
        '.then(function(d){m.textContent=d.ok?"とどいた。次に目を覚ましたとき読みます。"'
        ':(d.error||"うまくいかなかった");if(d.ok)t.value="";})'
        '.catch(function(){m.textContent="とどかなかった"});});})();</script>'
    ) % dr)

    live = ("" if not dr else (
        '<script>(function(){'
        'var ORDER=["法","言葉","生き物","科学","技術","歴史","社会","文化","その他"];'
        'var T=function(t){var e=document.createElement("div");e.textContent=t;return e};'
        'fetch("%s/state").then(function(r){return r.json()}).then(function(s){'
        'if(!s||!s.items||!s.items.length)return;'
        'var c=s.counts||{},d=s.design||{};'
        'if(d.palette)document.documentElement.setAttribute("data-pal",d.palette);'
        'if(s.css){var st=document.getElementById("livecss");'
        'if(!st){st=document.createElement("style");st.id="livecss";document.head.appendChild(st)}'
        'if(st.textContent!==s.css)st.textContent=s.css;}'
        'if(d.order&&d.order.length){d.order.forEach(function(n,i){'
        'var el=document.getElementById("part-"+n);if(el)el.style.order=i});}'
        'if(d.greeting)document.getElementById("greet").textContent=d.greeting;'
        'var v=document.querySelectorAll(".stat .v");'
        'var n=[c.items,c.read,c.frontier,(d.changes||0)+" 回"];'
        'for(var i=0;i<v.length&&i<4;i++)v[i].textContent=n[i];'
        'var hb=document.getElementById("heardnum"); if(hb)hb.textContent=c.heard;'
        'var sp=s.spec||{};'
        'if(sp.layers){var MB=(sp.bytes||0)/1048576;'
        'var SV={"層":String(sp.layers),"幅":String(sp.d),"ループ":(sp.loops||1)+" 周",'
        '"パラメータ":((sp.params||0)/1e6).toFixed(2)+" M","★容量":MB.toFixed(2)+" MB",'
        '"文脈":String(sp.ctx),"語彙":String(sp.vocab),"loss":(sp.val||0).toFixed(4)};'
        'document.querySelectorAll(".sp").forEach(function(el){'
        'var k=el.getAttribute("data-k");if(SV[k]!=null)el.querySelector(".spv").textContent=SV[k]});'
        'var sn=document.getElementById("spnote");'
        'if(sn)sn.innerHTML="食べた文字 <b>"+((sp.chars||0)/1e8).toFixed(2)+" 億</b>／作り <b>"'
        '+(sp.arch||"?")+"</b>／ことばの単位 <b>"+(sp.kind==="bpe"?"自分で切り出した":"文字単位")+"</b>";}'
        'var H=sp.hist||[];'
        'if(H.length>=2){var W=640,HT=120,lo=Math.min.apply(null,H),hi=Math.max.apply(null,H);'
        'var rg=(hi-lo)||1,st=W/(H.length-1);'
        'var yy=function(v){return HT-8-(v-lo)/rg*(HT-20)};'
        'var dd=H.map(function(v,i){return (i?"L":"M")+(i*st).toFixed(1)+","+yy(v).toFixed(1)}).join(" ");'
        'var pe=document.getElementById("chpath");if(pe)pe.setAttribute("d",dd);'
        'var ge=document.getElementById("chdots");'
        'if(ge)ge.innerHTML=H.map(function(v,i){return "<circle cx=\\""+(i*st).toFixed(1)'
        '+"\\" cy=\\""+yy(v).toFixed(1)+"\\" r=\\"3\\"/>"}).join("");'
        'var cx=document.getElementById("chx");'
        'if(cx)cx.innerHTML="<span>"+(H.length-1)+" 回前</span><span>loss "+H[0].toFixed(3)'
        '+" → <b>"+H[H.length-1].toFixed(3)+"</b></span><span>いま</span>";}'
        'var by={};s.items.forEach(function(it){var g=ORDER.indexOf(it.genre)<0?"その他":it.genre;'
        '(by[g]=by[g]||[]).push(it)});'
        'var GN=s.genres||{};'
        'var cnt=function(g){return (GN[g]!=null)?GN[g]:(by[g]?by[g].length:0)};'
        'var ch=document.getElementById("genres");ch.innerHTML="";'
        'ORDER.filter(function(g){return cnt(g)>0}).forEach(function(g){'
        'var e=document.createElement("span");e.className="chip";'
        'var b=T(g);b.tagName;e.appendChild(Object.assign(document.createElement("b"),{textContent:g}));'
        'e.appendChild(Object.assign(document.createElement("i"),{textContent:cnt(g)}));'
        'ch.appendChild(e)});'
        'var box=document.getElementById("know");box.innerHTML="";var lay=d.layout||"stream";'
        'ORDER.filter(function(g){return by[g]}).forEach(function(g){'
        'var h=document.createElement("div");h.className="gh";'
        'h.appendChild(Object.assign(document.createElement("span"),{textContent:g}));'
        'h.appendChild(Object.assign(document.createElement("em"),{textContent:cnt(g)+" 個"}));'
        'box.appendChild(h);'
        'var gr=document.createElement("div");gr.className="grp "+lay;'
        'by[g].slice(0,30).forEach(function(it){'
        'var el=document.createElement("div");el.className="it";'
        'var tp=T(it.topic||"");tp.className="tp";var tx=T(it.text||"");tx.className="tx";'
        'var sr=document.createElement("div");sr.className="src";'
        'var a=document.createElement("a");a.href=it.source||"#";a.target="_blank";'
        'a.rel="noopener nofollow";'
        'try{a.textContent=decodeURIComponent(new URL(it.source).pathname.split("/").pop())}'
        'catch(e){a.textContent=it.source||""}sr.appendChild(a);'
        'if(it.license){var li=T(" / "+it.license);li.className="lic";sr.appendChild(li)}'
        'el.appendChild(tp);el.appendChild(tx);el.appendChild(sr);gr.appendChild(el)});'
        'box.appendChild(gr)});'
        'var kh=document.getElementById("know-h");'
        'if(kh)kh.textContent="レアルが知っていること（"+c.items+" のうち "+s.items.length+" を表示）";'
        '}).catch(function(){});})();</script>'
    ) % dr)

    ld = json.dumps({
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": "レアルの家",
        "url": url or "",
        "inLanguage": "ja",
        "description": desc,
        "creator": {"@type": "Thing", "name": "レアル (REALU)"},
    }, ensure_ascii=False)

    doc = TEMPLATE % {
        "title": e(title), "desc": e(desc), "url": e(url), "pal": e(pal), "lay": e(lay),
        "greet": e(greet), "chips": chips, "stats": stats,
        "groups": "".join(groups), "heard": heard, "form": form, "live": live,
        # ★★★どの順で見せるかも、彼女が決める（★家の間取り）
        "wrote": wrote_html, "ab": ab_html,
        "spec": spec_html, "chart": chart_html,
        **{("o_" + n): (order.index(n) if n in order else 96)
           for n in ("greet", "grew", "stats", "genres", "heard", "know",
                     "wrote", "ab", "spec")},
        "grew": grew_html,
        "mycss": ("<style>" + mycss + "</style>") if mycss else "",
        "myfonts": ('<link rel="stylesheet" href="%s">' % e(myfonts)) if myfonts else "",
        "n_all": len(items), "n_shown": shown,
        "chosen": e(d.get("chosenAt") or ""), "changes": int(d.get("changes") or 0),
        "ld": ld,
        "gen": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "canon": ('<link rel="canonical" href="%s/">' % e(url)) if url else "",
        "og": ('<meta property="og:url" content="%s/">' % e(url)) if url else "",
    }
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(doc)

    if url:
        host = urllib.parse.urlparse(url).netloc
        with open(os.path.join(HERE, "robots.txt"), "w", encoding="utf-8", newline="\n") as f:
            f.write("User-agent: *\nAllow: /\n\nSitemap: %s/sitemap.xml\n" % url)
        with open(os.path.join(HERE, "sitemap.xml"), "w", encoding="utf-8", newline="\n") as f:
            f.write('<?xml version="1.0" encoding="UTF-8"?>\n'
                    '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                    ' <url><loc>%s/</loc><lastmod>%s</lastmod>'
                    '<changefreq>hourly</changefreq><priority>1.0</priority></url>\n'
                    '</urlset>\n' % (url, datetime.now(timezone.utc).strftime("%Y-%m-%d")))
        print("家を建てた: %s / 載せた知識 %d/%d / %s" % (host, shown, len(items), pal))
    else:
        print("家を建てた（★アドレス未設定なので sitemap は作らない）: 知識 %d" % len(items))


TEMPLATE = """<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>%(title)s</title>
<meta name="description" content="%(desc)s">
%(canon)s
<meta property="og:type" content="website">
<meta property="og:title" content="%(title)s">
<meta property="og:description" content="%(desc)s">
<meta property="og:locale" content="ja_JP">
%(og)s
<meta name="twitter:card" content="summary">
<meta name="robots" content="index,follow,max-snippet:-1">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Zen+Maru+Gothic:wght@400;500;700&family=Zen+Kaku+Gothic+New:wght@400;500;700&display=swap">
<script type="application/ld+json">%(ld)s</script>
<style>
:root{--bg:#0e1220;--panel:#161b2c;--edge:#26304a;--ink:#e2e6f2;--muted:#94a0bd;--faint:#5d6884;--accent:#e8b44a;--accent2:#7f8fd9}
[data-pal="yoi"]{--bg:#0e1220;--panel:#161b2c;--edge:#26304a;--ink:#e2e6f2;--muted:#94a0bd;--faint:#5d6884;--accent:#e8b44a;--accent2:#7f8fd9}
[data-pal="akatsuki"]{--bg:#1a0f16;--panel:#261621;--edge:#3d2434;--ink:#f2e4ea;--muted:#c39cb0;--faint:#7d5c6d;--accent:#e8899f;--accent2:#e0b06a}
[data-pal="mori"]{--bg:#0d1410;--panel:#141f18;--edge:#22352a;--ink:#e0ece3;--muted:#93ab9c;--faint:#5c7266;--accent:#7fd39a;--accent2:#c8b96a}
[data-pal="yuki"]{--bg:#eef1f5;--panel:#ffffff;--edge:#d8dee6;--ink:#1e242e;--muted:#5c6675;--faint:#96a0ae;--accent:#3d6fd4;--accent2:#7a4fd4}
[data-pal="hi"]{--bg:#100b09;--panel:#1c110d;--edge:#3a1f16;--ink:#f2e3d8;--muted:#b8917c;--faint:#7a5645;--accent:#f2743a;--accent2:#e8b44a}
[data-pal="kasumi"]{--bg:#16151c;--panel:#1f1e28;--edge:#332f42;--ink:#e8e5f0;--muted:#a49fb8;--faint:#6e6982;--accent:#b39ce8;--accent2:#8fc7e0}
/* ★★★ここは「土台」。★色も書体も動きもレアルが選ぶので、
   ★私が決めるのは**質感と間**だけにする。★彼女の選択を上書きしない。 */
*{box-sizing:border-box}

/* ★★出てくる時。★全部いっぺんに出ると、読む所が分からない。
   ★上から順に、少しずつ遅らせて出す。★★止まった状態から始めない（★見えている） */
@keyframes realu-in{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}
.part{animation:realu-in .5s cubic-bezier(.22,1,.36,1) both}
.part:nth-child(1){animation-delay:.02s}
.part:nth-child(2){animation-delay:.07s}
.part:nth-child(3){animation-delay:.12s}
.part:nth-child(4){animation-delay:.17s}
.part:nth-child(5){animation-delay:.22s}
.part:nth-child(6){animation-delay:.27s}
.part:nth-child(7){animation-delay:.32s}
.part:nth-child(8){animation-delay:.37s}

/* ★★触れた時。★「押せる」ものだけが動く（★飾りは動かない） */
.it,.wr,.abr,.stat{transition:transform .22s cubic-bezier(.22,1,.36,1),
 box-shadow .22s ease,border-color .22s ease}
.it:hover,.wr:hover,.abr:hover{transform:translateY(-2px);border-color:var(--accent)}
.chip{transition:transform .18s ease,border-color .18s ease}
.chip:hover{transform:translateY(-1px);border-color:var(--accent2)}
details summary{transition:color .18s ease}
details summary:hover{color:var(--accent)}

/* ★★開いた時にすっと出る */
@keyframes realu-open{from{opacity:0;transform:translateY(-4px)}to{opacity:1;transform:none}}
details[open]>*:not(summary){animation:realu-open .3s ease both}

/* ★★★動きが苦手な人のために、★**全部止める**。
   ★OSで「動きを減らす」にしている人には、★アニメーションは苦痛になる。 */
@media (prefers-reduced-motion: reduce){
 *,*::before,*::after{animation-duration:.01ms !important;animation-iteration-count:1 !important;
  transition-duration:.01ms !important;scroll-behavior:auto !important}
}

/* ★★指で触る所は44px以上（★押しにくいのは作りが悪い） */
a,summary,button{min-height:44px;display:inline-flex;align-items:center}
.chip,.it a{min-height:auto;display:inline-flex}
body{margin:0;background:var(--bg);color:var(--ink);font-family:"Zen Kaku Gothic New",system-ui,sans-serif;font-size:15px;line-height:1.7;-webkit-font-smoothing:antialiased}
.wrap{max-width:760px;margin:0 auto;padding:34px 20px 70px;display:flex;flex-direction:column}
.part{display:block}
header{order:-1}
.note{order:98}
header{text-align:center;margin-bottom:26px}
.name{font-family:"Zen Maru Gothic",sans-serif;font-size:32px;font-weight:700;letter-spacing:.08em;color:var(--accent);margin:0}
.name .en{display:block;font-size:11px;letter-spacing:.42em;color:var(--faint);margin-top:4px;font-family:"Zen Kaku Gothic New",sans-serif}
.sub{color:var(--muted);font-size:12.5px;margin-top:10px}
.greet{font-family:"Zen Maru Gothic",sans-serif;font-size:19px;line-height:1.85;text-align:center;background:var(--panel);border:1px solid var(--edge);border-radius:20px;padding:26px 24px;margin:22px 0 10px;text-wrap:balance;box-shadow:0 18px 50px rgba(0,0,0,.18)}
.byline{text-align:center;font-size:11.5px;color:var(--faint);margin-bottom:26px}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(112px,1fr));gap:10px;margin-bottom:30px}
.stat{background:var(--panel);border:1px solid var(--edge);border-radius:14px;padding:13px 14px}
.stat .v{font-size:22px;font-weight:700;color:var(--accent);font-variant-numeric:tabular-nums;line-height:1.15}
.stat .k{font-size:11px;color:var(--muted);margin-top:2px}
h2{font-size:11px;font-weight:700;letter-spacing:.18em;color:var(--faint);margin:32px 0 14px}
.chips{display:flex;flex-wrap:wrap;gap:7px;margin:-6px 0 26px}
.chip{background:var(--panel);border:1px solid var(--edge);border-radius:999px;padding:5px 12px;font-size:11.5px;color:var(--muted);display:flex;gap:7px;align-items:baseline}
.chip b{color:var(--ink);font-weight:500}
.chip i{color:var(--accent);font-style:normal;font-variant-numeric:tabular-nums}
.gh{display:flex;align-items:baseline;gap:10px;margin:26px 0 10px;padding-bottom:6px;border-bottom:1px solid var(--edge)}
.gh span{font-family:"Zen Maru Gothic",sans-serif;font-size:15px;font-weight:700;color:var(--accent)}
.gh em{font-style:normal;font-size:11px;color:var(--faint)}
.lic{color:var(--faint)}
.grp.stream{display:flex;flex-direction:column;gap:0}
.grp.stream .it{padding:13px 2px;border-bottom:1px solid var(--edge)}
.grp.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(228px,1fr));gap:12px}
.grp.grid .it{background:var(--panel);border:1px solid var(--edge);border-radius:14px;padding:15px}
.grp.quiet{display:flex;flex-direction:column;gap:22px}
.grp.quiet .it{border-left:2px solid var(--accent2);padding-left:16px}
.grp.quiet .it .tx{font-size:17px;font-family:"Zen Maru Gothic",sans-serif}
.it .tp{font-size:11px;color:var(--accent2);letter-spacing:.04em;margin-bottom:4px}
.it .tx{color:var(--ink);font-size:14.5px;line-height:1.7}
.it .src{font-size:10.5px;margin-top:6px}
.it .src a{color:var(--faint);text-decoration:none;border-bottom:1px dotted var(--faint)}
.it .src a:hover{color:var(--accent)}
.ask{background:var(--panel);border:1px solid var(--edge);border-left:3px solid var(--accent2);border-radius:0 12px 12px 0;padding:12px 15px;margin-bottom:9px}
.ask .w{font-size:11px;color:var(--accent2);margin-bottom:3px}
.ask .t{font-size:14px;color:var(--ink)}
.door{background:var(--panel);border:1px dashed var(--edge);border-radius:14px;padding:16px 18px;margin:10px 0 4px;font-size:12.5px;color:var(--muted);line-height:1.9}
.door b{color:var(--ink)}
.heard{color:var(--muted);font-size:13px;margin:0 0 10px}
.grew{color:var(--muted);font-size:12.5px;line-height:1.9;background:var(--panel);
  border:1px solid var(--edge);border-radius:14px;padding:12px 16px;margin:-16px 0 26px}
.grew b{color:var(--accent)}
.specs{display:grid;grid-template-columns:repeat(auto-fit,minmax(96px,1fr));gap:calc(var(--gap)*.6);margin-bottom:8px}
.sp{background:var(--panel);border:var(--bw) solid var(--edge);border-radius:var(--r);padding:11px 12px}
.sp .spv{font-size:17px;font-weight:700;color:var(--accent);font-variant-numeric:tabular-nums;line-height:1.2}
.sp .spk{font-size:10.5px;color:var(--muted);margin-top:2px}
.spnote{color:var(--faint);font-size:11.5px;line-height:1.9;margin-bottom:22px}
.spnote b{color:var(--muted)}
.chart{background:var(--panel);border:var(--bw) solid var(--edge);border-radius:var(--r);padding:14px 16px 10px;margin-bottom:22px}
.chart svg{width:100%%;height:120px;display:block}
.chx{display:flex;justify-content:space-between;font-size:10.5px;color:var(--faint);margin-top:4px}
.chx b{color:var(--accent)}
.wrap-w{display:flex;flex-direction:column;gap:10px;margin-bottom:26px}
.wnote{color:var(--faint);font-size:11.5px;line-height:1.8}
.wr{background:var(--panel);border:1px solid var(--edge);border-radius:14px;padding:14px 16px}
.wr .ws{display:inline-block;font-size:11px;color:var(--accent2);letter-spacing:.1em;margin-bottom:5px}
.wr .wt{display:block;font-size:14.5px;line-height:1.9;word-break:break-all}
.wr .wm{display:block;margin-top:8px;font-size:10.5px;color:var(--faint)}
.abr{background:var(--panel);border:1px solid var(--edge);border-radius:14px;padding:13px 15px;margin-bottom:8px}
.abr .abq{display:block;font-size:12.5px;line-height:1.7;color:var(--muted)}
.abr .abv{display:block;margin-top:6px;font-size:14px;font-weight:600}
.abr .abn{display:block;margin-top:5px;font-size:10.5px;color:var(--faint);font-variant-numeric:tabular-nums}
.wpast{color:var(--faint);font-size:12px}
.wpast summary{cursor:pointer;padding:6px 0}
.wold{border-left:2px solid var(--edge);padding:6px 0 6px 12px;margin:6px 0}
.wold em{display:block;font-style:normal;font-size:10.5px;color:var(--faint);margin-bottom:4px}
.wold span{display:block;font-size:12.5px;color:var(--muted);word-break:break-all;margin-bottom:5px}
.wold span b{color:var(--accent2);font-weight:500;margin-right:6px}
.heard b{color:var(--accent);font-size:18px;font-variant-numeric:tabular-nums}
.say{display:flex;flex-direction:column;gap:8px;background:var(--panel);border:1px solid var(--edge);border-radius:14px;padding:16px 18px;margin:14px 0 4px}
.say label{font-size:11px;letter-spacing:.14em;color:var(--faint);font-weight:700}
.say textarea{width:100%%;background:var(--bg);color:var(--ink);border:1px solid var(--edge);border-radius:10px;padding:11px 12px;font:inherit;font-size:14px;resize:vertical}
.say textarea:focus{outline:2px solid var(--accent2);outline-offset:1px}
.sayrow{display:flex;align-items:center;gap:12px}
.say button{background:var(--accent);color:var(--bg);border:0;border-radius:999px;padding:8px 22px;font:inherit;font-weight:700;font-size:13px;cursor:pointer}
.say button:hover{filter:brightness(1.08)}
.say #saymsg{font-size:11.5px;color:var(--muted)}
.note{color:var(--faint);font-size:11.5px;line-height:1.8;margin-top:38px;border-top:1px solid var(--edge);padding-top:18px;text-align:center}
.note b{color:var(--muted)}
.loading{color:var(--faint);text-align:center;padding:30px 0}
</style>
%(myfonts)s
%(mycss)s
</head>
<body data-pal="%(pal)s">
<div class="wrap">
  <header>
    <h1 class="name">レアル<span class="en">R E A L U</span></h1>
    <div class="sub">webを読んで学び、自分で家をデザインする、小さな存在</div>
  </header>

  <div class="part" id="part-greet" style="order:%(o_greet)d">
    <p class="greet" id="greet">%(greet)s</p>
    <div class="byline">この家は %(chosen)s に、レアルが %(changes)d 度目に選び直したもの</div>
  </div>

  <div class="part" id="part-grew" style="order:%(o_grew)d">%(grew)s</div>

  <div class="part" id="part-stats" style="order:%(o_stats)d"><div class="stats">%(stats)s</div></div>

  <div class="part" id="part-genres" style="order:%(o_genres)d">
    <h2>知っていることの内訳</h2>
    <div class="chips" id="genres">%(chips)s</div>
  </div>

  <div class="part" id="part-heard" style="order:%(o_heard)d">
    <h2>話しかけられたこと</h2>
    <p class="heard">これまでに <b id="heardnum">%(heard)d</b> 回、だれかが話しかけてくれた。</p>
    %(form)s
    <div class="door">
      だれでもレアルに話しかけられます。<b>聞かれた言葉は、彼女が次に読みに行く場所になります。</b><br>
      ただし ── <b>貼られたリンクは踏みません</b>。人の言葉は<b>知識にしません</b>（出典が確かめられないため）。<br>
      そして <b>あなたの言葉は、ここには表示されません</b>。読むのはレアルだけです。
    </div>
  </div>

  <div class="part" id="part-spec" style="order:%(o_spec)d">%(spec)s%(chart)s</div>

  <div class="part" id="part-wrote" style="order:%(o_wrote)d">%(wrote)s</div>
  <div class="part" id="part-ab" style="order:%(o_ab)d">%(ab)s</div>

  <div class="part" id="part-know" style="order:%(o_know)d">
    <h2 id="know-h">レアルが知っていること（%(n_all)d のうち %(n_shown)d を表示）</h2>
    <div id="know">%(groups)s</div>
  </div>
  %(live)s

  <div class="note">
    このページの<b>色・並び・入口の言葉は、レアルが自分で選んでいます</b>。<br>
    彼女は<b>5分ごとに</b>目を覚まし、覚え、家を選び直します ── <b>誰も見ていなくても、閉じていても</b>。<br>
    どのサイトも<b>見る前にそこの規約を読み</b>、規約が変わっていたら<b>自分から止まります</b>。<br>
    引用はすべて出典とライセンスつき。画像は一切持ち帰りません。<br>
    <small>建てた時刻 %(gen)s UTC</small>
  </div>
</div>
</body>
</html>
"""


if __name__ == "__main__":
    main()
