/**
 * IndexTTS 2.5 → Cloudflare Workers 网关
 * =======================================
 * 架构：Worker 只做"转发 + 轻量轮询"，避免超 CF 30 秒请求上限。
 *   POST /speech        -> 提交任务（runasync），立即返回 { jobId }
 *   GET  /audio/:jobId  -> 查询状态；完成时直接返回音频字节（audio/wav）
 *
 * 部署：wrangler deploy（需配置 KV 不需要；secret 二选一即可）
 * 环境变量：RUNPOD_API_KEY（必填）、ENDPOINT_ID（默认 indextts-2-5）
 */

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const key = env.RUNPOD_API_KEY;
    const endpointId = env.ENDPOINT_ID || "indextts-2-5";
    const base = `https://api.runpod.ai/v2/${endpointId}`;
    const cors = { "Access-Control-Allow-Origin": "*" };

    // ---------- POST /speech ：提交合成任务 ----------
    if (request.method === "POST" && url.pathname === "/speech") {
      let body;
      try { body = await request.json(); } catch { return json({ error: "invalid JSON" }, 400, cors); }

      const r = await fetch(`${base}/runasync`, {
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
      const jobId = m[1];
      const r = await fetch(`${base}/status/${jobId}`, {
        headers: { Authorization: `Bearer ${key}` },
      });
      const s = await r.json();
      if (s.status === "COMPLETED") {
        const out = s.output || {};
        if (out.audio_base64) {
          const bytes = Uint8Array.from(atob(out.audio_base64), (c) => c.charCodeAt(0));
          const mime = out.output_format === "mp3" ? "audio/mpeg" : out.output_format === "flac" ? "audio/flac" : "audio/wav";
          return new Response(bytes, { headers: { "Content-Type": mime, ...cors } });
        }
        return json({ error: "no audio in output", detail: out }, 502, cors);
      }
      if (s.status === "FAILED") {
        return json({ error: "synthesis failed", detail: s.output || s.error }, 500, cors);
      }
      // IN_PROGRESS / IN_QUEUE：客户端稍后重试
      return json({ status: s.status, jobId }, 202, cors);
    }

    return json({ routes: ["POST /speech", "GET /audio/:jobId"] }, 200, cors);
  },
};

function json(obj, status = 200, extra = {}) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { "Content-Type": "application/json", ...extra },
  });
}
