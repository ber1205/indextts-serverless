# IndexTTS 2.5 — RunPod Serverless（官方完整版）

> 零闲置成本（workersMin=0，无请求 0 计费）的官方 IndexTTS 2.5 语音克隆接口。
> 官方代码 index-tts/index-tts + 官方全量权重 IndexTeam/IndexTTS-2.5（含 Qwen 情绪模型），五语 + 全部情绪控制，功能零缺失。

## 架构总览

```
客户端 → Cloudflare Worker 网关 → RunPod Serverless 端点 → (AMPERE_24 GPU worker)
                                   POST /speech 提交         权重常驻网络卷(9GB)
                                   GET  /audio/:id 取音频    FlashBoot 秒级冷启动
                                                             无请求 workers=0 零计费
```

## 关键文件

| 文件 | 作用 |
|------|------|
| `Dockerfile` | 官方代码 + uv 依赖 + runpod==1.12.0（修复网络卷任务跟踪 bug）+ 构建期 import 自检 |
| `handler.py` | RunPod 入口：懒加载官方 IndexTTS2，权重自动下载到网络卷，全部官方参数透传 |
| `cloudflare-worker.js` | Cloudflare Workers 网关（runasync 提交 + 轮询取音频，规避 CF 30s 限制） |
| `wrangler.toml` | CF Worker 部署配置（ENDPOINT_ID=8zcxgnz7stl1jd） |
| `.github/workflows/build.yml` | 推送自动构建镜像到 GHCR（仅 Dockerfile/handler.py 变更触发） |

## 运行时管理脚本（在 /workspace 根目录）

| 脚本 | 用途 |
|------|------|
| `runpod_batch.py` | 批量配音执行（自动并发 + 断点续跑 + 失败重试 + --shutdown 省钱收尾） |
| `runpod_billing.py` | 计费采集（官方 v2 Billing API，增量存档 CSV，可配 cron） |

## 部署状态

- 端点：`8zcxgnz7stl1jd`（唯一，已删旧端点）
- GPU：AMPERE_24 池（US-WA-1，MIG 24GB，$0.69/hr）；16G 现货时可切 AMPERE_16（$0.58/hr）
- 网络卷：`697m3xn7j2`（US-WA-1，权重持久化）
- FlashBoot：已开启；workers：min=0 / max=2（无请求 0 计费，多用户自动扩容）
- 镜像：`ghcr.io/ber1205/indextts-2-5:latest`（GitHub 仓库 ber1205/indextts-serverless 承载构建与镜像，不可删除）

## 关键修复记录（曾导致部署失败的 3 个根因）

1. runpod SDK 1.7.11-1.10.0 网络卷端点任务跟踪 bug → 固定 `runpod==1.12.0`
2. uv pip install 未指定目标环境导致依赖装入系统 Python、容器启动即崩溃 → `--python /app/index-tts/.venv/bin/python`
3. 官方 IndexTTS2 类无 `eval()` 方法 → 移除 handler 中的 `m.eval()`

## API 调用

```
POST https://api.runpod.ai/v2/8zcxgnz7stl1jd/runsync
{"input": {"text": "...", "lang": "ZH", "prompt_audio": "<base64>", "output_format": "wav"}}
```

通过 Cloudflare 网关（浏览器可访问）：
```
POST https://indextts-gateway.ber1205.workers.dev/speech   → {jobId}
GET  https://indextts-gateway.ber1205.workers.dev/audio/:jobId → 轮询/取音频
GET  https://indextts-gateway.ber1205.workers.dev/health
```
