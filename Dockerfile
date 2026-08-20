# syntax=docker/dockerfile:1
# ===========================================================================
# IndexTTS 2.5 — RunPod Serverless（官方完整版，零功能缺失）· 多阶段瘦身
# ---------------------------------------------------------------------------
# GitHub 免费 runner 磁盘仅 14GB，两次失败均为 no space left on device。
# 策略：
#   - Stage1 builder：nvidia/cuda:12.8.1-devel（比 cudnn-devel 小约 6GB，
#     仅含编译 BigVGAN CUDA kernel 所需 nvcc）+ 官方代码/权重
#   - Stage2 runtime：nvidia/cuda:12.8.1-runtime（最小运行镜像）
#   - 关闭 GHA 层缓存（避免叠加占用磁盘）
# 官方全功能保留：五语、情感控制、拼音/音素标注、BigVGAN CUDA kernel
# ===========================================================================

# ---------------------------------------------------------------------------
# Stage 1 — 构建器
# ---------------------------------------------------------------------------
FROM nvidia/cuda:12.8.1-devel-ubuntu22.04 AS builder

ARG HF_ENDPOINT=https://huggingface.co

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HUB_ENABLE_HF_TRANSFER=1 \
    HF_ENDPOINT=${HF_ENDPOINT}

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3.10 python3.10-venv python3-pip \
        git ffmpeg curl ca-certificates build-essential cmake \
    && ln -sf /usr/bin/python3.10 /usr/bin/python3 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
RUN git clone --depth 1 https://github.com/index-tts/index-tts.git /app/index-tts
WORKDIR /app/index-tts
RUN python3 -m pip install --no-cache-dir -q uv \
    && (python3 -m uv sync --frozen 2>/dev/null || python3 -m uv sync)

COPY preload_models.py /app/preload_models.py
RUN /app/index-tts/.venv/bin/python /app/preload_models.py

# ---------------------------------------------------------------------------
# Stage 2 — 运行时
# ---------------------------------------------------------------------------
FROM nvidia/cuda:12.8.1-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PATH="/app/index-tts/.venv/bin:$PATH" \
    MODEL_DIR="/app/checkpoints" \
    PRELOAD="1"

RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /app/index-tts /app/index-tts
COPY --from=builder /app/checkpoints /app/checkpoints

COPY handler.py /app/index-tts/handler.py
COPY test_input.json /app/index-tts/test_input.json

WORKDIR /app/index-tts
EXPOSE 8000
CMD ["python", "-u", "handler.py"]
