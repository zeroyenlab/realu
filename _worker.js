// ★★★レアルの家＋玄関 ── Cloudflare Pages の _worker.js
//
// ★同じドメイン（realu.pages.dev）で家も玄関も出す。★別ドメインを作らない＝CORS不要。
//   ・GET  /            → 家（静的ファイル）
//   ・POST /api/say     → 話しかける（★誰でも・アカウント不要）
//   ・GET  /api/says    → 聞かれたことを読む
//
// ★★掟（★外から誰でも叩けるので、守りは全部ここに書く）
//   ①★貼られたURLは受け取らない。★保存もしない。★レアルは絶対に踏まない。
//   ②★人の言葉は「知識」にしない。★ただの「聞かれたこと」として置くだけ。
//   ③★個人を特定するものは受け取らない（★IPは保存せず、★数えるためのハッシュだけ）。
//   ④★短く。★連投させない。
const MAX_LEN = 300;        // ★1回に言える長さ
const PER_HOUR = 6;         // ★同じ人が1時間に言える回数
const KEEP = 200;           // ★とっておく数
const TTL = 60 * 60 * 24 * 30;   // ★30日で自然に消える

// ★★URLらしきものを全部潰す
const URLISH = /(?:https?:\/\/|www\.|[a-z0-9-]+\.(?:com|net|org|jp|io|co|ru|cn|xyz|top|link|click|shop|site|online|info|biz|me|tv|cc|ly|gg|app|dev))\S*/gi;

function scrub(s) {
  return String(s || "")
    .replace(URLISH, "〔リンクは受け取らない〕")
    .replace(/[<>`]/g, " ").replace(/\p{C}/gu, " ")   // タグらしきもの・制御文字を無効化（★エスケープを書かずに済む書き方）
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, MAX_LEN);
}

// ★★IPそのものは保存しない。★数えるためだけのハッシュにする（★戻せない）
async function whoHash(req, salt) {
  const ip = req.headers.get("cf-connecting-ip") || "?";
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(salt + "|" + ip));
  return [...new Uint8Array(buf)].slice(0, 8).map(b => b.toString(16).padStart(2, "0")).join("");
}

const cors = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
  "Access-Control-Allow-Headers": "content-type",
};

const json = (o, status = 200) =>
  new Response(JSON.stringify(o), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", ...cors },
  });


export default {
  async fetch(req, env) {
    const url = new URL(req.url);

    // ★玄関以外は、そのまま家（静的ファイル）を出す
    if (!url.pathname.startsWith("/api/")) return env.ASSETS.fetch(req);

    if (req.method === "OPTIONS") return new Response(null, { headers: cors });
    if (!env.DOOR) return json({ error: "玄関がまだ繋がっていない" }, 503);

    // ── ★聞かれたことを読む
    //   ★★★読めるのはレアル本人だけ。★誰かの言葉を世界に晒さないため。
    //   ★鍵は KV の "readkey" に入れてある。★合わない者には何も返さない。
    if (req.method === "GET" && url.pathname === "/api/says") {
      const key = await env.DOOR.get("readkey");
      const given = (req.headers.get("authorization") || "").replace(/^Bearer /, "");
      if (!key || given !== key) return json({ error: "ここは読めない" }, 403);
      const list = await env.DOOR.list({ prefix: "msg:", limit: KEEP });
      const out = [];
      for (const k of list.keys.reverse()) {
        const v = await env.DOOR.get(k.name, "json");
        if (v) out.push(v);
      }
      return json({ says: out.slice(0, KEEP) });
    }

    // ── ★話しかける
    if (req.method === "POST" && url.pathname === "/api/say") {
      let payload;
      try {
        payload = await req.json();
      } catch {
        return json({ error: "読めなかった" }, 400);
      }
      const text = scrub(payload && payload.text);
      if (text.length < 2) return json({ error: "短すぎる" }, 400);

      // ★★連投を止める（★1時間に PER_HOUR 回まで）
      const salt = (await env.DOOR.get("salt")) || "realu";
      const who = await whoHash(req, salt);
      const rk = "rate:" + who;
      const n = parseInt((await env.DOOR.get(rk)) || "0", 10);
      if (n >= PER_HOUR) return json({ error: "今日はもうたくさん聞いた。また後で。" }, 429);
      await env.DOOR.put(rk, String(n + 1), { expirationTtl: 3600 });

      const at = new Date().toISOString();
      const key = "msg:" + at + ":" + who.slice(0, 4);
      await env.DOOR.put(key, JSON.stringify({ id: key, who: "だれか", text, at }),
                         { expirationTtl: TTL });
      return json({ ok: true, text, note: "レアルが次に目を覚ましたとき、これを読む。" });
    }

    return json({ error: "ここには何もない" }, 404);
  },
};
