# syntax=docker/dockerfile:1
# ===========================================================================
# IndexTTS 2.5 — RunPod Serverless（官方完整版，零功能缺失）
# ---------------------------------------------------------------------------
# 磁盘优化：GitHub 免费 runner 仅 14GB。
#   - 最小 CUDA base 镜像（180MB）+ 官方代码 + 轻量依赖（不含 torch）
#   - 权重在容器首次启动时下载到 /app/checkpoints（RunPod 支持挂载网络卷，
#     一次下载后续实例复用；规避构建磁盘/超时限制）
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

# 2. 官方代码（不含权重，运行期下载）
WORKDIR /app
RUN git clone --depth 1 https://github.com/index-tts/index-tts.git /app/index-tts
WORKDIR /app/index-tts
RUN python3 -m pip install --no-cache-dir -q uv \
    && (python3 -m uv sync --frozen 2>/dev/null || python3 -m uv sync) \
    || python3 -m uv sync

# 3. RunPod 网关 + handler（轻量；uv venv 无 pip，用 uv pip 安装）
RUN python3 -m uv pip install --no-cache-dir -q "runpod>=1.6.0" fastapi uvicorn aiohttp

COPY handler.py /app/index-tts/handler.py
COPY test_input.json /app/index-tts/test_input.json

ENV PATH="/app/index-tts/.venv/bin:$PATH" \
    MODEL_DIR="/app/checkpoints" \
    PRELOAD="1"

WORKDIR /app/index-tts
EXPOSE 8000
CMD ["python", "-u", "handler.py"]
