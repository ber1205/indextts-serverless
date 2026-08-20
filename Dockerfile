# syntax=docker/dockerfile:1
# ===========================================================================
# IndexTTS 2.5 — RunPod Serverless（官方完整版，零功能缺失）
# ---------------------------------------------------------------------------
# 组成：
#   1. 官方代码库 index-tts/index-tts（uv 官方工作流，torch 2.8 + cu128）
#   2. 官方全量权重 IndexTeam/IndexTTS-2.5（含 qwen0.6bemo4-merge 情绪模型）
#   3. 辅助模型 w2v-bert-2.0 / campplus / bigvgan / MaskGCT codec（hf_cache）
#   4. RunPod 通信网关（runpod SDK）+ 自定义 handler
# 全部烘焙进镜像：运行期零下载，冷启动只加载显存。
# ===========================================================================
FROM nvidia/cuda:12.8.1-cudnn-devel-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HUB_ENABLE_HF_TRANSFER=1

# ---------------------------------------------------------------------------
# 1. 系统依赖（devel 镜像自带 nvcc，供 BigVGAN CUDA kernel 编译）
# ---------------------------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3.10 python3.10-venv python3-pip \
        git ffmpeg curl ca-certificates build-essential cmake \
    && ln -sf /usr/bin/python3.10 /usr/bin/python3 \
    && rm -rf /var/lib/apt/lists/*

# ---------------------------------------------------------------------------
# 2. 官方代码 + 官方 uv 依赖（torch 2.8 cu128、全量多语言文本处理链）
# ---------------------------------------------------------------------------
WORKDIR /app
RUN git clone --depth 1 https://github.com/index-tts/index-tts.git /app/index-tts
WORKDIR /app/index-tts
RUN pip install -q uv && (uv sync --frozen 2>/dev/null || uv sync)

# ---------------------------------------------------------------------------
# 3. 烘焙官方全量权重 -> /app/checkpoints（含 qwen 情绪子模型）
#    （中国网络可加 --build-arg 或环境变量 HF_ENDPOINT=https://hf-mirror.com）
# ---------------------------------------------------------------------------
COPY preload_models.py /app/preload_models.py
RUN /app/index-tts/.venv/bin/python /app/preload_models.py

# ---------------------------------------------------------------------------
# 4. RunPod 网关 + handler
# ---------------------------------------------------------------------------
RUN /app/index-tts/.venv/bin/pip install -q "runpod>=1.6.0" fastapi uvicorn aiohttp

COPY handler.py /app/index-tts/handler.py
COPY test_input.json /app/index-tts/test_input.json

ENV PATH="/app/index-tts/.venv/bin:$PATH" \
    MODEL_DIR="/app/checkpoints" \
    PRELOAD="1"

WORKDIR /app/index-tts
EXPOSE 8000
CMD ["python", "-u", "handler.py"]
