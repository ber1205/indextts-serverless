"""
构建期脚本：下载官方 IndexTTS-2.5 全量权重 + 辅助模型到 /app/checkpoints。
- 官方权重：IndexTeam/IndexTTS-2.5（完整快照，含 qwen0.6bemo4-merge 情绪模型）
- 辅助模型：官方 model_download.py 自动下载到 checkpoints/hf_cache
  （w2v-bert-2.0、campplus_cn_common.bin、bigvgan、MaskGCT semantic codec）
- 下载源：海外直连 HuggingFace；中国大陆自动走 ModelScope/hf-mirror（官方自动切换）
"""
import os

MODEL_DIR = os.environ.get("MODEL_DIR", "/app/checkpoints")

if __name__ == "__main__":
    print(f">> MODEL_DIR = {MODEL_DIR}")

    # 1) 官方全量权重
    from huggingface_hub import snapshot_download

    print(">> [1/2] downloading official IndexTeam/IndexTTS-2.5 (complete snapshot, incl. qwen emotion model) ...")
    snapshot_download("IndexTeam/IndexTTS-2.5", local_dir=MODEL_DIR)
    print(">> [1/2] official weights done")

    # 2) 辅助模型（官方自动切换 HF / ModelScope）
    from indextts.utils.model_download import ensure_models_available

    print(">> [2/2] downloading auxiliary models (w2v-bert-2.0 / campplus / bigvgan / maskgct codec) ...")
    paths = ensure_models_available(MODEL_DIR)
    for k, v in paths.items():
        print(f">>     aux [{k}] -> {v}")

    print(">> ALL WEIGHTS READY")
