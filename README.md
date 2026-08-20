# IndexTTS 2.5 — RunPod Serverless（官方完整版）

> 零闲置成本（Min Workers=0，无请求 0 计费）的官方 IndexTTS 2.5 语音克隆接口。
> 官方代码 + 官方全量权重（含 Qwen 情绪模型）全部烘焙进镜像，运行期零下载、零功能缺失。

## 项目文件

| 文件 | 作用 |
|------|------|
| `Dockerfile` | 官方代码库 + uv 官方依赖 + 全量权重烘焙 + RunPod 网关 |
| `handler.py` | RunPod 入口（官方 IndexTTS2，全部官方参数透传） |
| `preload_models.py` | 构建期下载官方权重 + 辅助模型（HF/ModelScope 自动切换） |
| `deploy_runpod.py` | 一键创建 RunPod Template + Endpoint（GraphQL API） |
| `build_push.sh` | 本地构建 + 推送 GHCR（**唯一需要你在自己电脑做的步骤**） |
| `cloudflare-worker.js` | Cloudflare Workers 对接网关（异步提交 + 轮询取音频） |
| `test_input.json` | RunPod 本地测试样例 |

## 部署流程（4 步）

### 第 1 步：构建镜像并推送 GHCR（你的电脑，约 30-50 分钟）

```bash
# 需安装 Docker（无需 GPU）；中国大陆先执行：
export HF_ENDPOINT=https://hf-mirror.com

export GHCR_TOKEN="<你的 GitHub Token>"
bash build_push.sh
```

完成后把输出中的镜像地址发回给 AI（如 `ghcr.io/ber1205/indextts-2-5:latest`）。

### 第 2 步：创建 RunPod Serverless 端点（AI 帮你执行）

```bash
export RUNPOD_API_KEY="<你的 RunPod API Key>"
python deploy_runpod.py
```

默认配置（可在环境变量覆盖）：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| GPU | `NVIDIA RTX 4000 Ada Generation` | 20GB，社区价约 **$0.20/小时** |
| Min Workers | `0` | 无请求 0 实例，**0 计费** |
| Max Workers | `2` | 最大并发 2 |
| Idle Timeout | `300` 秒 | 5 分钟无请求自动缩到 0 |
| Scale Timeout | `600` 秒 | 冷启动最长等待 |

更便宜的备选：`NVIDIA RTX A5000`（24GB，$0.16/h）、`NVIDIA GeForce RTX 3090`（24GB，$0.22/h）。

### 第 3 步：测试接口

```bash
# 同步调用（冷启动约 2-5 分钟，之后 1-3 秒）
curl -X POST "https://api.runpod.ai/v2/indextts-2-5/runsync" \
  -H "Authorization: Bearer $RUNPOD_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "input": {
      "text": "你好，这是官方 IndexTTS 2.5 的克隆声音。",
      "lang": "ZH",
      "prompt_audio_url": "https://example.com/voice_sample.wav"
    }
  }'
```

### 第 4 步：Cloudflare Workers 对接

把 `cloudflare-worker.js` 部署到 CF，配置两个变量：
- `RUNPOD_API_KEY`（Secret）
- `ENDPOINT_ID` = `indextts-2-5`

```bash
npx wrangler secret put RUNPOD_API_KEY
npx wrangler deploy cloudflare-worker.js
```

调用方式（异步，规避 CF 30 秒限制）：

```bash
# 1. 提交任务 -> { jobId }
curl -X POST "https://<your-worker>.workers.dev/speech" \
  -H "Content-Type: application/json" \
  -d '{"text":"你好","lang":"ZH","prompt_audio_url":"https://..."}'

# 2. 轮询（完成时直接返回音频字节 audio/wav；进行中返回 202 + status）
curl "https://<your-worker>.workers.dev/audio/<jobId>" --output out.wav
```

## API 参数（官方全功能透传）

| 参数 | 默认 | 说明 |
|------|------|------|
| `text` | 必填 | 合成文本，支持 `<行\|XING2>` 拼音/音素标注 |
| `lang` | `ZH` | `ZH`/`EN`/`JA`/`ES`/`AR` |
| `prompt_audio` / `prompt_audio_url` | 必填其一 | 声音克隆参考音频（base64 或 URL，5-10 秒） |
| `emo_control_method` | `0` | `0`无 `1`情感音频 `2`情感向量 `3`情感文本 |
| `emo_audio` / `emo_audio_url` | - | 情感参考音频（method=1） |
| `emo_vector` | - | 8 维情感向量（method=2） |
| `emo_text` | - | 情感文本（method=3，官方 Qwen 情绪模型已内置） |
| `emo_alpha` | `1.0` | 情感强度 |
| `speed` | `1.0` | 语速 0.5-2.0（映射 duration_factor=1/speed） |
| `duration_factor` | `1.0` | 官方时长因子 |
| `interval_silence` | `200` | 句间静音 ms |
| `max_text_tokens_per_segment` | `120` | 单段最大 token |
| `text_normalization` | `true` | 文本正则 |
| `output_format` | `wav` | `wav`/`mp3`/`flac` |

返回：`audio_base64`（音频）、`sample_rate`、`duration_sec`、`infer_sec`、`lang`。

## 成本与冷启动

- 无请求：**0 计费**（Worker 缩到 0）
- 有请求：GPU 按秒计费（RTX 4000 Ada 约 $0.20/h = 单次合成几厘美元）
- 冷启动（长时间无请求后第一单）：拉镜像 + 模型加载，约 2-5 分钟，`scaleTimeout` 已设 600 秒兜底
- 预热后：1-3 秒响应

## 镜像内容（官方完整、无功能缺失）

- 官方代码：`index-tts/index-tts`（`indextts.infer_v2_5.IndexTTS2`，torch 2.8 + cu128，uv 官方工作流）
- 官方全量权重：`IndexTeam/IndexTTS-2.5`（`gpt.pth`、`s2mel.pth`、`codec.pth`、`feat1/2.pt`、`config.yaml`、`qwen0.6bemo4-merge/` 情绪模型等全部文件）
- 辅助模型：`w2v-bert-2.0`、`campplus_cn_common.bin`、`bigvgan_v2_22khz_80band_256x`、MaskGCT semantic codec（`checkpoints/hf_cache/`）
- 全部 `local_files_only=True` 离线加载，运行期不依赖任何外部下载

## 常见问题

- **Q：为什么不用 vLLM？** A：vllm-omni 目前支持的 TTS 列表里还没有 IndexTTS 2.5（官方 8/10 刚发布）；社区 vLLM 转换项目最高只到 IndexTTS-2。为保证"官方最完整、无功能缺失"，本方案使用官方原生推理（BF16），在 RTX 4000 Ada 上已足够快。官方后续若正式支持 vLLM，可平滑切换。
- **Q：为什么选 RTX 4000 Ada？** A：20GB 显存足够（模型 bf16 峰值约 6-8GB），社区价最低档（$0.20/h）。
- **Q：构建失败怎么办？** A：最常见原因是网络（HF 超时），中国大陆构建前设置 `HF_ENDPOINT=https://hf-mirror.com`；uv 锁文件异常时 `uv sync` 会兜底。

## 安全提醒

部署完成后，请**立即吊销/重置**你在聊天中贴出的 GitHub Token 与 RunPod API Key：
- GitHub：Settings → Developer settings → Personal access tokens
- RunPod：Settings → API Keys

## 参考

- 官方代码：[github.com/index-tts/index-tts](https://github.com/index-tts/index-tts)
- 官方权重：[huggingface.co/IndexTeam/IndexTTS-2.5](https://huggingface.co/IndexTeam/IndexTTS-2.5)
- RunPod Serverless：[docs.runpod.io](https://docs.runpod.io/serverless/overview)
