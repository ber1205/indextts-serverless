"""
IndexTTS 2.5 — RunPod Serverless Handler（官方完整版）
=====================================================
基于官方代码库 index-tts/index-tts 的 `indextts.infer_v2_5.IndexTTS2`，
全量加载官方权重（含 qwen 情绪模型、w2v-bert、campplus、bigvgan），
功能无缺失：中/英/日/西/阿 五语、情感向量/情感音频/情感文本、拼音/音素标注、
语速（duration_factor）、停顿控制、文本正则等官方全部参数均透传。

运行方式（RunPod Serverless）：
    python handler.py   -> runpod.serverless.start({"handler": handler})

本地调试（可选）：
    python handler.py   -> 同时启动 FastAPI：GET /health、POST /v1/audio/speech
"""

import base64
import io
import json
import logging
import os
import tempfile
import threading
import time
import urllib.request

# ---------------------------------------------------------------------------
# 日志
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("indextts-serverless")

# ---------------------------------------------------------------------------
# 全局配置（镜像内已烘焙权重）
# ---------------------------------------------------------------------------
MODEL_DIR = os.environ.get("MODEL_DIR", "/app/checkpoints")
PRELOAD = os.environ.get("PRELOAD", "1") == "1"          # 容器启动即后台预加载
LANG_CODES = ("ZH", "EN", "JA", "ES", "AR")

_model = None
_model_lock = threading.Lock()


# ===========================================================================
# 模型管理（懒加载 + 启动预加载 + 线程安全）
# ===========================================================================
def _load_model():
    """加载官方 IndexTTS2（bf16）。首次调用会较慢，之后常驻显存。"""
    global _model
    if _model is None:
        import torch
        from indextts.infer_v2_5 import IndexTTS2

        t0 = time.time()
        logger.info("Loading official IndexTTS 2.5 from %s ...", MODEL_DIR)
        m = IndexTTS2(
            cfg_path=os.path.join(MODEL_DIR, "config.yaml"),
            model_dir=MODEL_DIR,
            use_bf16=True,          # 官方 bf16：显存/速度最优
            use_cuda_kernel=True,   # BigVGAN fused CUDA kernel（镜像含 nvcc，失败自动回退）
            use_qwen_emo=True,      # 加载官方 Qwen 情绪模型（emo-text 控制必需）
        )
        m.eval()
        _model = m
        logger.info("Model ready in %.1fs", time.time() - t0)
    return _model


def _boot_preload():
    """容器启动后台预加载；失败则首个任务时按需加载。"""
    try:
        _load_model()
    except Exception:
        logger.exception("Boot preload failed; will lazy-load on first job.")


def get_model():
    with _model_lock:
        return _load_model()


if PRELOAD:
    threading.Thread(target=_boot_preload, daemon=True).start()


# ===========================================================================
# 小工具
# ===========================================================================
def _write_tmp(b64_or_path: str, suffix: str) -> str:
    """base64 字符串或本地路径 -> 临时文件路径"""
    fd, path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    with open(path, "wb") as f:
        f.write(base64.b64decode(b64_or_path))
    return path


def _download(url: str, suffix: str) -> str:
    fd, path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    with urllib.request.urlopen(url, timeout=120) as r, open(path, "wb") as f:
        f.write(r.read())
    return path


def _resolve_audio(src: str, is_url: bool, suffix: str = ".wav"):
    if not src:
        return None
    return _download(src, suffix) if is_url else _write_tmp(src, suffix)


def _wav_bytes(sr: int, audio_np, fmt: str = "wav") -> bytes:
    """写 WAV（MP3 由 ffmpeg 后端支持，默认 WAV 最稳）。"""
    import soundfile as sf

    buf = io.BytesIO()
    fmt = (fmt or "wav").lower()
    if fmt not in ("wav", "mp3", "flac"):
        fmt = "wav"
    sf.write(buf, audio_np, sr, format=fmt)
    return buf.getvalue()


# ===========================================================================
# 核心推理编排（官方参数全透传）
# ===========================================================================
def synthesize(req: dict) -> dict:
    """
    输入（RunPod event.input / FastAPI body）：
        text                  必填，合成文本（支持 <字|拼音> 发音标注）
        lang                  默认 "ZH"，ZH/EN/JA/ES/AR
        prompt_audio          必填，声音克隆参考音频 base64（或 prompt_audio_url 远程 URL）
        prompt_audio_url      参考音频远程地址（二选一）
        emo_control_method    0=无情绪 1=情感音频 2=情感向量 3=情感文本（默认 0）
        emo_audio / emo_audio_url  情感参考音频（method=1）
        emo_vector            [8] 维度情感向量（method=2）
        emo_text              情感文本（method=3，需官方 Qwen 情绪模型，镜像已内置）
        emo_alpha             情感强度 0-1（默认 1.0）
        use_random            情感随机（默认 false）
        speed                 语速倍率 0.5-2.0（内部映射为 duration_factor=1/speed）
        duration_factor       官方时长因子（默认 1.0，与 speed 二选一）
        interval_silence      句间静音 ms（默认 200）
        max_text_tokens_per_segment  单段最大 token（默认 120）
        text_normalization    文本正则（默认 true）
        output_format         wav/mp3/flac（默认 wav）
    """
    text = str(req.get("text", "")).strip()
    if not text:
        raise ValueError("text 不能为空")
    lang = str(req.get("lang", "ZH")).upper()
    if lang not in LANG_CODES:
        raise ValueError(f"lang 仅支持 {LANG_CODES}，收到 {lang}")

    prompt_audio = req.get("prompt_audio")
    prompt_audio_url = req.get("prompt_audio_url")
    if not prompt_audio and not prompt_audio_url:
        raise ValueError("prompt_audio（base64）或 prompt_audio_url 必填，用于声音克隆")

    spk_path = _resolve_audio(prompt_audio, False) if prompt_audio else _resolve_audio(prompt_audio_url, True)
    tmp_paths = [p for p in (spk_path,) if p]

    emo_control_method = int(req.get("emo_control_method", 0))
    emo_audio_path = None
    if emo_control_method == 1:
        emo_audio = req.get("emo_audio")
        emo_audio_url = req.get("emo_audio_url")
        if not emo_audio and not emo_audio_url:
            raise ValueError("emo_control_method=1 需要 emo_audio 或 emo_audio_url")
        emo_audio_path = _resolve_audio(emo_audio, False) if emo_audio else _resolve_audio(emo_audio_url, True)
        tmp_paths.append(emo_audio_path)

    emo_vector = req.get("emo_vector") if emo_control_method == 2 else None
    use_emo_text = emo_control_method == 3
    emo_text = req.get("emo_text") if use_emo_text else None

    duration_factor = float(req.get("duration_factor", 1.0))
    speed = req.get("speed")
    if speed is not None:
        s = float(speed)
        if not 0.5 <= s <= 2.0:
            raise ValueError("speed 需在 0.5-2.0 之间")
        duration_factor = duration_factor / s

    model = get_model()
    try:
        t0 = time.time()
        sr, wav = model.infer(
            spk_audio_prompt=spk_path,
            text=text,
            output_path=None,
            lang=lang,
            emo_audio_prompt=emo_audio_path,
            emo_alpha=float(req.get("emo_alpha", 1.0)),
            emo_vector=emo_vector,
            use_emo_text=use_emo_text,
            emo_text=emo_text,
            use_random=bool(req.get("use_random", False)),
            interval_silence=int(req.get("interval_silence", 200)),
            max_text_tokens_per_segment=int(req.get("max_text_tokens_per_segment", 120)),
            duration_factor=duration_factor,
            text_normalization=bool(req.get("text_normalization", True)),
            verbose=False,
        )
        infer_sec = time.time() - t0
        logger.info("infer ok: %s chars, %.1fs, sr=%s", len(text), infer_sec, sr)
    finally:
        for p in tmp_paths:
            if p and os.path.exists(p):
                os.remove(p)

    fmt = str(req.get("output_format", "wav")).lower()
    audio_bytes = _wav_bytes(sr, wav, fmt)
    duration_sec = round(len(wav) / sr, 3) if getattr(wav, "ndim", 1) == 1 else round(wav.shape[0] / sr, 3)

    return {
        "status": "success",
        "audio_base64": base64.b64encode(audio_bytes).decode("ascii"),
        "output_format": fmt if fmt in ("wav", "mp3", "flac") else "wav",
        "sample_rate": int(sr),
        "duration_sec": duration_sec,
        "infer_sec": round(infer_sec, 2),
        "lang": lang,
    }


# ===========================================================================
# RunPod Serverless 入口
# ===========================================================================
def handler(event: dict) -> dict:
    """RunPod 网关调用：event['input'] 为上述请求体。"""
    job_input = event.get("input", event)
    try:
        return synthesize(job_input)
    except Exception as e:
        logger.exception("job failed")
        return {"status": "failed", "error": f"{type(e).__name__}: {e}"}


# ===========================================================================
# 本地调试（FastAPI）
# ===========================================================================
def _make_fastapi_app():
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse

    app = FastAPI(title="IndexTTS 2.5 (official) — RunPod Serverless", version="2.5.0")

    @app.get("/health")
    async def health():
        return {"status": "ok" if _model is not None else "loading", "model_dir": MODEL_DIR}

    @app.post("/v1/audio/speech")
    async def tts(req: Request):
        try:
            body = await req.json()
        except Exception:
            return JSONResponse({"status": "failed", "error": "invalid JSON"}, status_code=400)
        try:
            return synthesize(body)
        except Exception as e:
            return JSONResponse({"status": "failed", "error": f"{type(e).__name__}: {e}"}, status_code=500)

    return app


if __name__ == "__main__":
    import runpod

    if os.environ.get("LOCAL_HTTP", "0") == "1":
        import uvicorn

        app = _make_fastapi_app()
        logger.info("local HTTP mode on 0.0.0.0:8000")
        uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
    else:
        logger.info("Starting RunPod serverless gateway ...")
        runpod.serverless.start({"handler": handler})
