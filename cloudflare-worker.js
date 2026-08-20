/**
 * IndexTTS 2.5 → Cloudflare Workers 网关（v2, Service Worker 格式）
 * =================================================================
 * 架构：Worker 只做"转发 + 轻量轮询"，规避 CF 30 秒请求上限。
 *   POST /speech          -> 提交合成任务（runasync），立即返回 { jobId }
 *   GET  /audio/:jobId    -> 查询状态；完成时直接返回音频字节（audio/wav）
 *   GET  /health          -> 健康检查（端点 worker 数/队列数）
 *   GET  /                -> 路由说明
 *
 * 环境变量（在 Workers 控制台 > Settings > Variables and Secrets）：
 *   RUNPOD_API_KEY  RunPod API Key（必填，存为 Secret）
 *   ENDPOINT_ID     可选，默认 8zcxgnz7stl1jd（v3 主端点）
 */
addEventListener("fetch", (event) => {
  event.respondWith(handleRequest(event.request));
});

async function handleRequest(request) {
  const url = new URL(request.url);
  const key = RUNPOD_API_KEY;
  const endpointId = typeof ENDPOINT_ID !== "undefined" && ENDPOINT_ID ? ENDPOINT_ID : "8zcxgnz7stl1jd";
  const base = `https://api.runpod.ai/v2/${endpointId}`;
  const cors = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization",
  };

  // CORS 预检
  if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: cors });

  // ---------- GET /health ：健康检查 ----------
  if (request.method === "GET" && url.pathname === "/health") {
    try {
      const h = await fetch(`${base}/health`, { headers: { Authorization: `Bearer ${key}` } });
      const d = await h.json();
      return json({ ok: h.ok, endpoint: endpointId, ...d }, h.ok ? 200 : 502, cors);
    } catch (e) {
      return json({ ok: false, error: String(e) }, 502, cors);
    }
  }

  // ---------- POST /speech ：提交合成任务 ----------
  if (request.method === "POST" && url.pathname === "/speech") {
    if (!key) return json({ error: "RUNPOD_API_KEY not configured" }, 500, cors);
    let body;
    try { body = await request.json(); } catch { return json({ error: "invalid JSON" }, 400, cors); }
    if (!body || !body.text) return json({ error: "text is required" }, 400, cors);

    const r = await fetch(`${base}/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${key}` },
      body: JSON.stringify({ input: body }),
    });
    const d = await r.json();
    if (r.ok && d.id) return json({ jobId: d.id }, 200, cors);
    return json({ error: "kickoff failed", detail: d.error || d }, 502, cors);
  }

  // ---------- GET /audio/:jobId ：查询/取音频 ----------
  const m = url.pathname.match(/^\/audio\/([^/]+)$/);
  if (m && request.method === "GET") {
    if (!key) return json({ error: "RUNPOD_API_KEY not configured" }, 500, cors);
    const jobId = m[1];
    const r = await fetch(`${base}/status/${jobId}`, {
      headers: { Authorization: `Bearer ${key}` },
    });
    const s = await r.json();
    if (s.status === "COMPLETED") {
      const out = s.output || {};
      if (out.audio_base64) {
        try {
          const bytes = Uint8Array.from(atob(out.audio_base64), (c) => c.charCodeAt(0));
          const mime = out.output_format === "mp3" ? "audio/mpeg"
                     : out.output_format === "flac" ? "audio/flac"
                     : "audio/wav";
          return new Response(bytes, { headers: { "Content-Type": mime, ...cors } });
        } catch {
          return json({ error: "bad audio_base64" }, 502, cors);
        }
      }
      return json({ error: "no audio in output", detail: out }, 502, cors);
    }
    if (s.status === "FAILED") {
      return json({ error: "synthesis failed", detail: s.output || s.error }, 500, cors);
    }
    // IN_QUEUE / IN_PROGRESS：客户端稍后轮询
    return json({ status: s.status, jobId }, 202, cors);
  }

  return json({ service: "indextts-2.5-gateway", routes: ["POST /speech", "GET /audio/:jobId", "GET /health"] }, 200, cors);
}

function json(obj, status = 200, extra = {}) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { "Content-Type": "application/json", ...extra },
  });
}
