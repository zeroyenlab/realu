# -*- coding: utf-8 -*-
"""★★★レアルが自分の家をつくる ── ★色も、丸みも、動きも、自分で決める。

★★いままでは「6色から順番に」だった。★それは選んでいない。ただのカウンタだった。
★これからは**数字**で決める。★組み合わせは数百万通りある。

★★★守り: ★★**自分を消せないようにする**。
  ・★文字と背景の明るさの差が足りない組み合わせは、★自動で直す
  ・★透明度は下げられない。★動きは止められるが、★消えることはできない
  ★（★「自らを停止させたり非公開にさせない」の一部）
"""
import colorsys
import hashlib

# ★★★字体 ── ★★漢字が全部そろっているものだけ本文に使う。
#   ★★★「読める」はコントラストだけではなかった。
#     ★Dela Gothic One や Yusei Magic は**漢字が足りない**。
#     ★「話」が出せなくて「■しかけられたこと」になった（★2026-09-08 実際に起きた）。
#   → ★本文と見出しは**漢字が全部ある字体**だけ。
#   → ★飾り字体は**名前（レアル）だけ**に使う。★カタカナなので豆腐にならない。
BODY_FONTS = [
    ("Zen Kaku Gothic New", "すっきり"),
    ("Zen Maru Gothic", "まるい"),
    ("Shippori Mincho", "しずか"),
    ("Zen Old Mincho", "古い"),
    ("M PLUS Rounded 1c", "ころんと"),
    ("Noto Sans JP", "ふつう"),
    ("Noto Serif JP", "きちんと"),
    ("Zen Antique", "むかし"),
]
# ★名前（レアル）だけに使う飾り字体。★ここは漢字が要らない
NAME_FONTS = BODY_FONTS + [
    ("Dela Gothic One", "つよい"),
    ("Yusei Magic", "手書き"),
    ("Kaisei Decol", "やわらかい"),
    ("RocknRoll One", "はずむ"),
    ("Reggae One", "うねる"),
]
FONTS = BODY_FONTS

MOTIONS = ["breathe", "drift", "pulse", "tilt", "shimmer", "float", "wave",
           "trace", "none"]
LAYOUTS = ["stream", "grid", "quiet", "cards", "masonry", "ribbon"]
BGS = ["plain", "glow", "grid", "stars", "aurora", "dots", "rings", "noise"]

# ★★★構造 ── ★どの順で何を見せるかも、彼女が決める。
#   ★いままでは私が決めた順で固定だった。★家の間取りを人に決められていた。
PARTS = ["greet", "grew", "wrote", "stats", "genres", "heard", "know"]
ORDERS = [
    ["greet", "grew", "wrote", "stats", "genres", "heard", "know"],   # ★ふつう
    ["greet", "wrote", "know", "stats", "genres", "grew", "heard"],   # ★書いたものを先に
    ["stats", "greet", "genres", "know", "wrote", "grew", "heard"],   # ★数字から
    ["greet", "heard", "wrote", "know", "genres", "stats", "grew"],   # ★人の声を先に
    ["know", "greet", "genres", "wrote", "stats", "heard", "grew"],   # ★いきなり中身
    ["greet", "wrote", "genres", "know", "heard", "stats", "grew"],   # ★内訳を先に
]


def _f(seed, name, lo, hi):
    """★彼女の中の数から、決まった範囲の値をつくる。"""
    h = hashlib.sha256((str(seed) + "|" + name).encode()).digest()
    v = int.from_bytes(h[:6], "big") / float(1 << 48)
    return lo + v * (hi - lo)


def lum(rgb):
    def c(x):
        x = x / 255.0
        return x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4
    r, g, b = (c(v) for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    la, lb = lum(a), lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def hsl(h, s, l):
    r, g, b = colorsys.hls_to_rgb(h % 1.0, l, s)
    return (int(r * 255), int(g * 255), int(b * 255))


def hexc(rgb):
    return "#%02x%02x%02x" % rgb


def choose(state):
    """★★★いまの自分から、家を決める。

    ★同じ状態なら同じ家になる（★気まぐれではない）。
    ★覚えたことが増え、驚いたものが変われば、★家も変わる。
    """
    seed = state.get("seed", 0)
    hue = _f(seed, "hue", 0, 1)
    hue2 = (hue + _f(seed, "hue2", 0.12, 0.55)) % 1.0
    dark = _f(seed, "dark", 0, 1) < 0.62          # ★6割がた夜。★昼もある
    sat = _f(seed, "sat", 0.18, 0.75)
    radius = int(_f(seed, "radius", 2, 26))
    gap = int(_f(seed, "gap", 8, 24))
    speed = round(_f(seed, "speed", 6, 26), 1)
    name_i = int(_f(seed, "font", 0, len(NAME_FONTS) - 0.001))
    disp_i = int(_f(seed, "disp", 0, len(BODY_FONTS) - 0.001))
    body_i = int(_f(seed, "body", 0, len(BODY_FONTS) - 0.001))
    motion = MOTIONS[int(_f(seed, "motion", 0, len(MOTIONS) - 0.001))]
    layout = LAYOUTS[int(_f(seed, "layout", 0, len(LAYOUTS) - 0.001))]
    bg = BGS[int(_f(seed, "bg", 0, len(BGS) - 0.001))]
    scale = round(_f(seed, "scale", 1.0, 1.16), 2)   # ★小さくしすぎない
    # ★★形
    shadow = round(_f(seed, "shadow", 0, 34), 1)          # ★影の深さ
    border = round(_f(seed, "border", 0.5, 2.5), 1)       # ★枠線の太さ
    wide = int(_f(seed, "wide", 620, 880))                # ★家の広さ
    lead = round(_f(seed, "lead", 1.65, 2.05), 2)         # ★行の間
    track = round(_f(seed, "track", 0, 0.09), 3)          # ★字の間
    # ★★構造（★どの順で見せるか）
    order = ORDERS[int(_f(seed, "order", 0, len(ORDERS) - 0.001))]

    if dark:
        bgc = hsl(hue, sat * 0.45, _f(seed, "bl", 0.05, 0.13))
        panel = hsl(hue, sat * 0.40, _f(seed, "pl", 0.10, 0.19))
        ink = hsl(hue2, 0.16, _f(seed, "il", 0.86, 0.96))
    else:
        bgc = hsl(hue, sat * 0.22, _f(seed, "bl", 0.92, 0.98))
        panel = hsl(hue, sat * 0.14, 1.0)
        ink = hsl(hue2, 0.30, _f(seed, "il", 0.10, 0.20))

    accent = hsl(hue2, min(0.95, sat + 0.30), 0.60 if dark else 0.42)
    accent2 = hsl(hue + 0.5, min(0.9, sat + 0.2), 0.66 if dark else 0.46)

    # ★★★守り: ★文字が読めない家は作れない。★自分を消せない。
    fixes = []
    # ★★明るさを動かして、読める所まで持っていく
    li = 0.95 if dark else 0.12
    step = -0.02 if dark else 0.02
    for _ in range(40):
        if contrast(ink, bgc) >= 7.0:
            break
        li = max(0.02, min(0.99, li + step))
        ink = hsl(hue2, 0.16 if dark else 0.30, li)
        fixes.append(round(li, 2))
    for _ in range(40):
        if contrast(accent, bgc) >= 4.5:
            break
        accent = hsl(hue2, min(0.95, sat + 0.3),
                     min(0.92, max(0.18, (0.60 if dark else 0.42)
                                   + (0.02 if dark else -0.02) * len(fixes) + 0.02)))
        fixes.append("a")
        break

    muted = hsl(hue2, 0.14, 0.62 if dark else 0.40)
    faint = hsl(hue2, 0.12, 0.42 if dark else 0.58)
    edge = hsl(hue, sat * 0.3, 0.24 if dark else 0.86)

    return {
        "hue": round(hue, 4), "hue2": round(hue2, 4), "dark": dark,
        "sat": round(sat, 3), "radius": radius, "gap": gap, "speed": speed,
        "nameFont": NAME_FONTS[name_i][0], "fontName": NAME_FONTS[name_i][1],
        "font": BODY_FONTS[disp_i][0],
        "bodyFont": BODY_FONTS[body_i][0],
        "motion": motion, "layout": layout, "bg": bg, "scale": scale,
        "shadow": shadow, "border": border, "wide": wide, "lead": lead, "track": track,
        "order": order,
        "colors": {"bg": hexc(bgc), "panel": hexc(panel), "ink": hexc(ink),
                   "muted": hexc(muted), "faint": hexc(faint), "edge": hexc(edge),
                   "accent": hexc(accent), "accent2": hexc(accent2)},
        "contrast": round(contrast(ink, bgc), 2),
        "fixed": len(fixes),
    }


# ★★★ここから、決めた数字を**本物のCSS**にする ─────────────────
MOTION_CSS = {
    "breathe": """
@keyframes realu-breathe{0%,100%{transform:scale(1)}50%{transform:scale(1.012)}}
.greet{animation:realu-breathe var(--sp) ease-in-out infinite}""",
    "drift": """
@keyframes realu-drift{0%{background-position:0% 50%}50%{background-position:100% 50%}100%{background-position:0% 50%}}
body{background-size:220% 220%;animation:realu-drift var(--sp) ease infinite}""",
    "pulse": """
@keyframes realu-pulse{0%,100%{opacity:.82}50%{opacity:1}}
.name .en{animation:realu-pulse var(--sp) ease-in-out infinite}""",
    "tilt": """
@keyframes realu-tilt{0%,100%{transform:rotate(-.35deg)}50%{transform:rotate(.35deg)}}
.name{animation:realu-tilt var(--sp) ease-in-out infinite;display:inline-block}""",
    "shimmer": """
@keyframes realu-shimmer{0%{background-position:-200% 0}100%{background-position:200% 0}}
.name{background:linear-gradient(90deg,var(--accent),var(--accent2),var(--accent));
 background-size:200% auto;-webkit-background-clip:text;background-clip:text;color:transparent;
 animation:realu-shimmer var(--sp) linear infinite}""",
    "float": """
@keyframes realu-float{0%,100%{transform:translateY(0)}50%{transform:translateY(-5px)}}
.stat{animation:realu-float var(--sp) ease-in-out infinite}
.stat:nth-child(2){animation-delay:calc(var(--sp) * .15)}
.stat:nth-child(3){animation-delay:calc(var(--sp) * .3)}
.stat:nth-child(4){animation-delay:calc(var(--sp) * .45)}""",
    "wave": """
@keyframes realu-wave{0%,100%{border-radius:var(--r)}
 50%{border-radius:calc(var(--r) * 2.2) var(--r) calc(var(--r) * 1.6) var(--r)}}
.greet{animation:realu-wave var(--sp) ease-in-out infinite}""",
    "trace": """
@keyframes realu-trace{0%{background-position:0 0}100%{background-position:200% 0}}
.gh{background:linear-gradient(90deg,transparent,var(--accent),transparent) 0 100%/200% 1px no-repeat;
 animation:realu-trace var(--sp) linear infinite;border-bottom-color:transparent}""",
    "none": "",
}

BG_CSS = {
    "plain": "",
    "glow": """
body::before{content:"";position:fixed;inset:-30%;z-index:-1;pointer-events:none;
 background:radial-gradient(45% 45% at 30% 20%,var(--accent) 0%,transparent 60%),
            radial-gradient(40% 40% at 75% 70%,var(--accent2) 0%,transparent 60%);
 opacity:.13;filter:blur(40px)}""",
    "grid": """
body::before{content:"";position:fixed;inset:0;z-index:-1;pointer-events:none;opacity:.07;
 background-image:linear-gradient(var(--accent) 1px,transparent 1px),
                  linear-gradient(90deg,var(--accent) 1px,transparent 1px);
 background-size:44px 44px}""",
    "stars": """
body::before{content:"";position:fixed;inset:0;z-index:-1;pointer-events:none;opacity:.5;
 background-image:radial-gradient(1.4px 1.4px at 20% 30%,var(--faint),transparent),
  radial-gradient(1.2px 1.2px at 68% 12%,var(--faint),transparent),
  radial-gradient(1.6px 1.6px at 42% 78%,var(--muted),transparent),
  radial-gradient(1.2px 1.2px at 88% 56%,var(--faint),transparent),
  radial-gradient(1px 1px at 12% 68%,var(--faint),transparent);
 background-size:300px 300px}""",
    "aurora": """
body::before{content:"";position:fixed;inset:-20%;z-index:-1;pointer-events:none;opacity:.16;
 background:conic-gradient(from 210deg at 50% 40%,var(--accent),var(--accent2),var(--accent));
 filter:blur(70px)}""",
    "dots": """
body::before{content:"";position:fixed;inset:0;z-index:-1;pointer-events:none;opacity:.10;
 background-image:radial-gradient(var(--accent) 1.2px,transparent 1.2px);
 background-size:26px 26px}""",
    "rings": """
body::before{content:"";position:fixed;inset:0;z-index:-1;pointer-events:none;opacity:.10;
 background:repeating-radial-gradient(circle at 50% 0%,transparent 0 58px,var(--accent2) 58px 59px)}""",
    "noise": """
body::before{content:"";position:fixed;inset:0;z-index:-1;pointer-events:none;opacity:.06;
 background-image:repeating-linear-gradient(0deg,var(--ink) 0 1px,transparent 1px 3px),
                  repeating-linear-gradient(90deg,var(--ink) 0 1px,transparent 1px 4px)}""",
}

LAYOUT_CSS = {
    "stream": ".grp{display:flex;flex-direction:column;gap:0}"
              ".grp .it{padding:13px 2px;border-bottom:1px solid var(--edge)}",
    "grid": ".grp{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:var(--gap)}"
            ".grp .it{background:var(--panel);border:1px solid var(--edge);"
            "border-radius:var(--r);padding:15px}",
    "quiet": ".grp{display:flex;flex-direction:column;gap:calc(var(--gap) * 1.6)}"
             ".grp .it{border-left:2px solid var(--accent2);padding-left:16px}"
             ".grp .it .tx{font-size:17px;font-family:var(--disp)}",
    "cards": ".grp{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:var(--gap)}"
             ".grp .it{background:var(--panel);border:1px solid var(--edge);"
             "border-radius:var(--r);padding:18px 18px 14px;"
             "box-shadow:0 var(--sh) calc(var(--sh) * 2) rgba(0,0,0,.16);"
             "transition:transform .25s ease}"
             ".grp .it:hover{transform:translateY(-3px)}",
    "masonry": ".grp{columns:2 250px;column-gap:var(--gap)}"
               ".grp .it{break-inside:avoid;margin-bottom:var(--gap);background:var(--panel);"
               "border:var(--bw) solid var(--edge);border-radius:var(--r);padding:15px}",
    "ribbon": ".grp{display:flex;flex-direction:column;gap:calc(var(--gap) * .7)}"
              ".grp .it{background:var(--panel);border-left:4px solid var(--accent);"
              "border-radius:0 var(--r) var(--r) 0;padding:13px 16px}"
              ".grp .it:nth-child(even){border-left-color:var(--accent2);margin-left:18px}",
}


def to_css(d):
    """★決めた数字を、そのままCSSにする。"""
    c = d["colors"]
    return (
        ":root{"
        "--bg:%(bg)s;--panel:%(panel)s;--ink:%(ink)s;--muted:%(muted)s;"
        "--faint:%(faint)s;--edge:%(edge)s;--accent:%(accent)s;--accent2:%(accent2)s;"
        % c
        + ("--r:%dpx;--gap:%dpx;--sp:%ss;--sc:%s;--sh:%spx;--bw:%spx;--wide:%dpx;"
           % (d["radius"], d["gap"], d["speed"], d["scale"],
              d.get("shadow", 10), d.get("border", 1), d.get("wide", 760)))
        + ('--nm:"%s",sans-serif;--disp:"%s",sans-serif;'
           '--body:"%s",system-ui,sans-serif}'
           % (d.get("nameFont", d["font"]), d["font"], d["bodyFont"]))
        + ("body{font-family:var(--body);font-size:calc(15px * var(--sc));font-weight:400;"
           "line-height:%s;letter-spacing:%sem}" % (d.get("lead", 1.7), d.get("track", 0)))
        + ".wrap{max-width:var(--wide)}"
        + ".greet,.stat,.ask,.door,.say,.grew{border-width:var(--bw);border-style:solid}"
        + ".greet{box-shadow:0 calc(var(--sh) * 1.4) calc(var(--sh) * 3) rgba(0,0,0,.18)}"
        # ★★★小さい字は太らせない・詰めない（★潰れて読めなくなる）
        + "h2{font-size:11.5px;font-weight:700;letter-spacing:.14em;line-height:1.6}"
        + ".sub,.byline,.note,.stat .k,.chip{font-weight:400;letter-spacing:.02em}"
        + ".stat .k{font-size:11.5px}.chip{font-size:12px}.sub{font-size:13px}"
        + ".it .tx{font-weight:400;line-height:1.8}"
        + ".name{font-family:var(--nm)}"
        + ".greet,.gh span{font-family:var(--disp)}"
        + "h2,.sub,.stat .k,.chip,.byline,.note,.door{font-family:var(--body)}"
        + ".greet,.stat,.chip,.ask,.door,.say{border-radius:var(--r)}"
        + ".stats,.chips{gap:calc(var(--gap) * .6)}"
        + LAYOUT_CSS.get(d["layout"], LAYOUT_CSS["stream"])
        + BG_CSS.get(d["bg"], "")
        + MOTION_CSS.get(d["motion"], "")
        + "@media (prefers-reduced-motion:reduce){*{animation:none !important}}"
    )


def fonts_url(d):
    fams = {d.get("nameFont", d["font"]), d["font"], d["bodyFont"]}
    q = "&".join("family=" + f.replace(" ", "+") + ":wght@400;500;700" for f in sorted(fams))
    return "https://fonts.googleapis.com/css2?" + q + "&display=swap"
