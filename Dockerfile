# syntax=docker/dockerfile:1
# ===========================================================================
# IndexTTS 2.5 — RunPod Serverless（官方完整版，零功能缺失，权重全量烘焙）
# ---------------------------------------------------------------------------
# 磁盘策略（GitHub 免费 runner 仅 14GB，workflow 已先清理无用工具腾空间）：
#   - 最小 CUDA base 镜像（180MB）+ 官方代码 + 轻量依赖
#   - 官方全量权重（IndexTeam/IndexTTS-2.5 + 辅助模型 w2v-bert/campplus/bigvgan
#     + qwen 情绪模型）在【构建期】下载烘焙进镜像，运行期零下载，
#     彻底解决 RunPod Serverless 冷启动超时导致的 worker 反复崩溃
#   - BigVGAN 走官方 torch 回退（use_cuda_kernel=False，无推理损失）
# ===========================================================================
FROM nvidia/cuda:12.8.1-base-ubuntu22.04

ARG HF_ENDPOINT=https://huggingface.co

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_ENDPOINT=${HF_ENDPOINT}

# 1. 系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3.10 python3.10-venv python3-pip \
        git ffmpeg curl ca-certificates build-essential \
    && ln -sf /usr/bin/python3.10 /usr/bin/python3 \
    && rm -rf /var/lib/apt/lists/*

# 2. 官方代码 + uv 依赖（不含权重）
WORKDIR /app
RUN git clone --depth 1 https://github.com/index-tts/index-tts.git /app/index-tts
WORKDIR /app/index-tts
RUN python3 -m pip install --no-cache-dir -q uv \
    && (python3 -m uv sync --frozen 2>/dev/null || python3 -m uv sync) \
    || python3 -m uv sync

# 3. 构建期烘焙官方全量权重（运行期零下载）
#    主权重 snapshot_download 到 /app/checkpoints，辅助模型由官方
#    ensure_models_available 下载到 /app/checkpoints/hf_cache
RUN python3 -m uv pip install --no-cache-dir -q "huggingface-hub[cli,hf_xet]" \
    && mkdir -p /app/checkpoints \
    && .venv/bin/python -c "import huggingface_hub; huggingface_hub.snapshot_download('IndexTeam/IndexTTS-2.5', local_dir='/app/checkpoints')" \
    && .venv/bin/python -c "from indextts.utils.model_download import ensure_models_available; ensure_models_available('/app/checkpoints')" \
    && rm -rf /root/.cache/huggingface \
    && echo ">> Official IndexTTS 2.5 weights baked into image"

# 4. RunPod 网关 + handler（轻量）
RUN python3 -m uv pip install --no-cache-dir -q "runpod>=1.6.0" fastapi uvicorn aiohttp

COPY handler.py /app/index-tts/handler.py
COPY test_input.json /app/index-tts/test_input.json

ENV PATH="/app/index-tts/.venv/bin:$PATH" \
    MODEL_DIR="/app/checkpoints" \
    PRELOAD="1"

WORKDIR /app/index-tts
EXPOSE 8000
CMD ["python", "-u", "handler.py"]
