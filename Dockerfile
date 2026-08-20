# syntax=docker/dockerfile:1
# ===========================================================================
# IndexTTS 2.5 — RunPod Serverless（官方完整版，零功能缺失）
# ---------------------------------------------------------------------------
# 磁盘优化版：GitHub 免费 runner 仅 14GB，devel 镜像 10GB 会爆盘。
# 方案：nvidia/cuda:12.8.1-base（约 180MB，最小 CUDA 运行时）
#   + BigVGAN 走官方 torch 回退实现（use_cuda_kernel=False，
#     官方代码 index-tts 自带 alias_free_activation/torch，推理无损失）
#   + 权重烘焙 /app/checkpoints
# ===========================================================================
FROM nvidia/cuda:12.8.1-base-ubuntu22.04

ARG HF_ENDPOINT=https://huggingface.co

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HUB_ENABLE_HF_TRANSFER=1 \
    HF_ENDPOINT=${HF_ENDPOINT}

# 1. 系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3.10 python3.10-venv python3-pip \
        git ffmpeg curl ca-certificates build-essential \
    && ln -sf /usr/bin/python3.10 /usr/bin/python3 \
    && rm -rf /var/lib/apt/lists/*

# 2. 官方代码 + uv 依赖
WORKDIR /app
RUN git clone --depth 1 https://github.com/index-tts/index-tts.git /app/index-tts
WORKDIR /app/index-tts
RUN python3 -m pip install --no-cache-dir -q uv \
    && (python3 -m uv sync --frozen 2>/dev/null || python3 -m uv sync)

# 3. 烘焙官方全量权重（含 qwen 情绪模型 + hf_cache 辅助模型）
COPY preload_models.py /app/preload_models.py
# hf_transfer 加速权重下载（HF_HUB_ENABLE_HF_TRANSFER=1 需要；uv venv 无 pip，用 uv pip 安装）
RUN python3 -m uv pip install --no-cache-dir -q hf_transfer
RUN /app/index-tts/.venv/bin/python /app/preload_models.py

# 4. RunPod 网关 + handler
RUN /app/index-tts/.venv/bin/pip install -q "runpod>=1.6.0" fastapi uvicorn aiohttp

COPY handler.py /app/index-tts/handler.py
COPY test_input.json /app/index-tts/test_input.json

ENV PATH="/app/index-tts/.venv/bin:$PATH" \
    MODEL_DIR="/app/checkpoints" \
    PRELOAD="1"

WORKDIR /app/index-tts
EXPOSE 8000
CMD ["python", "-u", "handler.py"]
