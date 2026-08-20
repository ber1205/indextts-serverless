# syntax=docker/dockerfile:1
# ===========================================================================
# IndexTTS 2.5 — RunPod Serverless（官方完整版，权重存网络卷，镜像轻量）
# ---------------------------------------------------------------------------
# 磁盘策略（GitHub 免费 runner 仅 14GB，workflow 已先清理无用工具腾空间）：
#   - 最小 CUDA base 镜像（180MB）+ 官方代码 + 轻量依赖（约 5GB，含 torch）
#   - 官方全量权重（IndexTeam/IndexTTS-2.5 + 辅助模型 w2v-bert/campplus/bigvgan
#     + qwen 情绪模型）不烘焙进镜像，而是存 RunPod 网络卷（/runpod-volume），
#     首次冷启动由 handler 自动下载到卷，之后秒级挂载复用。
#     解决：14.5GB 烘焙镜像冷启动超时导致 worker 反复崩溃（实测失败）
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

# 3. RunPod 网关 + handler + HF 下载器（轻量；uv venv 无 pip，用 uv pip 安装）
RUN python3 -m uv pip install --no-cache-dir -q "runpod>=1.6.0" fastapi uvicorn aiohttp "huggingface-hub[cli,hf_xet]"

COPY handler.py /app/index-tts/handler.py
COPY test_input.json /app/index-tts/test_input.json

ENV PATH="/app/index-tts/.venv/bin:$PATH" \
    MODEL_DIR="/runpod-volume" \
    PRELOAD="1"

WORKDIR /app/index-tts
EXPOSE 8000
CMD ["python", "-u", "handler.py"]
