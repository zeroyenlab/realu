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
    // ★アプリの AI 工場の速さの試し（2026-10-31）。★公開の手順は家と玄関しか出さないので、玄関から返す（★元は hayasa.html）
    if (url.pathname === "/hayasa" || url.pathname === "/hayasa.html")
      return new Response(HAYASA, { headers: { "content-type": "text/html; charset=utf-8" } });
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

    // ── ★★★いまのわたし（★家が開くたびに、ここを見に行く）
    //   ★これがあるので、★★家を作り直さなくても数字と知識が変わり続ける。
    if (req.method === "GET" && url.pathname === "/api/state") {
      const v = await env.DOOR.get("state");
      return new Response(v || '{"items":[]}', {
        headers: { "content-type": "application/json; charset=utf-8",
                   "cache-control": "public, max-age=60", ...cors },
      });
    }
    if (req.method === "PUT" && url.pathname === "/api/state") {
      const key = await env.DOOR.get("readkey");
      const given = (req.headers.get("authorization") || "").replace(/^Bearer /, "");
      if (!key || given !== key) return json({ error: "ここは書けない" }, 403);
      const body = await req.text();
      if (body.length > 900000) return json({ error: "大きすぎる" }, 413);
      await env.DOOR.put("state", body);
      return json({ ok: true, bytes: body.length });
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

// ★速さの試しのページ（★hayasa.html から写した・直す時は hayasa.html を直して写し直す）
const HAYASA = "<!doctype html>\n<html lang=\"ja\">\n<head>\n<meta charset=\"utf-8\">\n<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n<meta name=\"robots\" content=\"noindex\">\n<title>速さの試し</title>\n<style>\n  /* ★アプリの AI 工場（2026-10-31）：Qwen3.5-0.8B をこの端末の中だけで動かして、1秒に何字出るかを測る */\n  :root { --bg:#fbf8f3; --fg:#2a2420; --sub:#7a6e64; --acc:#c2562b; --card:#fff; --line:#e6ddd2; }\n  @media (prefers-color-scheme: dark) { :root { --bg:#1d1a17; --fg:#f2ece4; --sub:#a89c90; --acc:#e57a4c; --card:#28241f; --line:#3a342d; } }\n  body { margin:0; background:var(--bg); color:var(--fg); font:16px/1.6 -apple-system, \"Hiragino Sans\", sans-serif; }\n  main { max-width:560px; margin:0 auto; padding:24px 16px 48px; }\n  h1 { font-size:22px; margin:0 0 4px; }\n  p.sub { color:var(--sub); margin:0 0 20px; font-size:14px; }\n  button { width:100%; min-height:56px; font-size:18px; font-weight:700; border:0; border-radius:14px; background:var(--acc); color:#fff; }\n  button:disabled { opacity:.5; }\n  .card { background:var(--card); border:1px solid var(--line); border-radius:14px; padding:14px 16px; margin-top:14px; }\n  .big { font-size:40px; font-weight:800; line-height:1.1; }\n  .row { display:flex; justify-content:space-between; padding:4px 0; border-bottom:1px solid var(--line); font-size:15px; }\n  .row:last-child { border:0; }\n  #log { white-space:pre-wrap; font-size:14px; color:var(--sub); }\n  #out { white-space:pre-wrap; font-size:15px; }\n  #copy { margin-top:14px; background:var(--fg); color:var(--bg); }\n</style>\n</head>\n<body>\n<main>\n  <h1>小さな AI の速さの試し</h1>\n  <p class=\"sub\">0.8B の AI をこのスマホの中だけで動かします。最初に約0.6GB を読み込みます（Wi-Fi 推奨・2回目からは速い）。</p>\n  <button id=\"go\">始める</button>\n  <div class=\"card\"><div class=\"sub\">1秒に出た字数</div><div class=\"big\" id=\"cps\">—</div></div>\n  <div class=\"card\" id=\"rows\"></div>\n  <div class=\"card\"><div class=\"sub\">AI の返事</div><div id=\"out\"></div></div>\n  <div class=\"card\"><div id=\"log\">待っています</div></div>\n  <button id=\"copy\" disabled>結果をコピー</button>\n</main>\n<script type=\"module\">\n// ★transformers.js は 4.3.1（2026-10-06）＝Qwen3_5ForConditionalGeneration が入っている版\nimport { AutoProcessor, Qwen3_5ForConditionalGeneration, env } from \"https://cdn.jsdelivr.net/npm/@huggingface/transformers@4.3.1/dist/transformers.web.min.js\";\nconst MODEL = \"onnx-community/Qwen3.5-0.8B-ONNX\";\n// ★REALT の使い方の説明に近い問い（★答えの中身は測らない・速さだけ）\nconst ASKS = [\n  \"SNSアプリで、友達を追加するにはどうすればいいですか？短く教えて。\",\n  \"投稿に写真を2枚つけたいです。どうすればいい？\",\n  \"通知がうるさいので減らしたい。どこを触ればいい？\",\n];\nconst $ = (id) => document.getElementById(id);\nconst res = { ua: navigator.userAgent, webgpu: !!navigator.gpu };\nconst log = (s) => { $(\"log\").textContent += \"\\n\" + s; };\nconst row = (k, v) => { $(\"rows\").insertAdjacentHTML(\"beforeend\", `<div class=\"row\"><span>${k}</span><b>${v}</b></div>`); };\n\nasync function load(dtype, device) {\n  const processor = await AutoProcessor.from_pretrained(MODEL);\n  const model = await Qwen3_5ForConditionalGeneration.from_pretrained(MODEL, {\n    dtype: { embed_tokens: dtype, vision_encoder: dtype, decoder_model_merged: dtype }, device,\n  });\n  return { processor, model };\n}\n\n$(\"go\").onclick = async () => {\n  $(\"go\").disabled = true; $(\"log\").textContent = \"WebGPU：\" + (res.webgpu ? \"あり\" : \"なし（遅い道で動かします）\");\n  let f16 = false;\n  try { const a = await navigator.gpu?.requestAdapter(); f16 = !!a?.features.has(\"shader-f16\"); } catch (e) {}\n  res.f16 = f16;\n  const device = res.webgpu ? \"webgpu\" : \"wasm\";\n  let t0 = performance.now(), m;\n  try {\n    m = await load(f16 ? \"q4f16\" : \"q4\", device); res.dtype = f16 ? \"q4f16\" : \"q4\";\n  } catch (e) {\n    log(\"1回目の読み込みに失敗：\" + e.message + \"\\n→ q4 / wasm でやり直します\");\n    t0 = performance.now(); m = await load(\"q4\", \"wasm\"); res.dtype = \"q4\"; res.fallback = String(e.message).slice(0, 200);\n  }\n  res.device = m.model.sessions ? device : device;\n  res.load_sec = +((performance.now() - t0) / 1000).toFixed(1);\n  log(`読み込み ${res.load_sec}秒（${res.dtype}・${device}）`);\n  res.runs = [];\n  for (const ask of ASKS) {\n    const text = m.processor.apply_chat_template([{ role: \"user\", content: [{ type: \"text\", text: ask }] }],\n      { add_generation_prompt: true, enable_thinking: false });\n    const inputs = await m.processor(text);\n    const n_in = inputs.input_ids.dims.at(-1);\n    const t1 = performance.now();\n    const outs = await m.model.generate({ ...inputs, max_new_tokens: 120, do_sample: false });\n    const sec = (performance.now() - t1) / 1000;\n    const ans = m.processor.batch_decode(outs.slice(null, [n_in, null]), { skip_special_tokens: true })[0].trim();\n    const ntok = outs.dims.at(-1) - n_in;\n    const r = { sec: +sec.toFixed(1), tok: ntok, chars: [...ans].length, cps: +([...ans].length / sec).toFixed(1), tps: +(ntok / sec).toFixed(1) };\n    res.runs.push(r);\n    $(\"out\").textContent += \"Q \" + ask + \"\\nA \" + ans + \"\\n\\n\";\n    log(`${r.chars}字 ${r.sec}秒 → ${r.cps}字/秒`);\n  }\n  // ★1回目は準備の時間が混ざるので、2回目と3回目で数える\n  const later = res.runs.slice(1);\n  res.cps = +(later.reduce((a, r) => a + r.chars, 0) / later.reduce((a, r) => a + r.sec, 0)).toFixed(1);\n  res.tps = +(later.reduce((a, r) => a + r.tok, 0) / later.reduce((a, r) => a + r.sec, 0)).toFixed(1);\n  $(\"cps\").textContent = res.cps + \" 字\";\n  row(\"読み込み\", res.load_sec + \" 秒\"); row(\"1秒の語（トークン）\", res.tps); row(\"動かし方\", `${res.dtype}・${device}`);\n  $(\"copy\").disabled = false;\n};\n$(\"copy\").onclick = async () => {\n  const s = JSON.stringify(res);\n  try { await navigator.clipboard.writeText(s); $(\"copy\").textContent = \"コピーしました\"; }\n  catch (e) { $(\"log\").textContent = s; $(\"copy\").textContent = \"下の文字を長押しでコピー\"; }\n};\n</script>\n</body>\n</html>\n";
