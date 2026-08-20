#!/usr/bin/env python3
"""
本地测试脚本 —— 无需 RunPod SDK，直接调用 handler 逻辑。
用法：
    python test_local.py --text "你好世界" --language ZH
"""

import argparse
import json
import os
import sys

# 添加项目路径
sys.path.insert(0, os.path.dirname(__file__))

from handler import _load_model, _handle_inference, handler


def test_with_text(text: str, language: str = "ZH", speed: float = 1.0):
    """简单文本测试"""
    print(f"[INFO] 开始合成: {text[:50]}...")
    event = {
        "input": {
            "text": text,
            "language": language,
            "output_format": "wav",
            "speed": speed,
            "emo_vector": [0, 0, 0, 0, 0, 0, 0, 0],
        }
    }
    result = handler(event)
    print(f"[OK] 合成完成: {result}")
    return result


def test_batch():
    """批量测试多语言"""
    tests = [
        ("ZH", "大家好，我是 IndexTTS 2.5 语音合成系统，很高兴为您服务。"),
        ("EN", "Hello, this is a voice cloning demo powered by IndexTTS 2.5."),
        ("JA", "こんにちは、IndexTTS 2.5 の音声合成デモです。"),
        ("ES", "Hola, esta es una demostración de síntesis de voz con IndexTTS 2.5."),
    ]
    for lang, text in tests:
        print(f"\n{'='*60}")
        print(f"[TEST] Language: {lang}")
        print(f"       Text: {text}")
        test_with_text(text, lang)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test IndexTTS 2.5 locally")
    parser.add_argument("--text", type=str, default="你好世界", help="Text to synthesise")
    parser.add_argument("--lang", type=str, default="ZH", choices=["ZH", "EN", "JA", "ES", "AR"])
    parser.add_argument("--speed", type=float, default=1.0, help="Speech speed (0.5-2.0)")
    parser.add_argument("--batch", action="store_true", help="Run multi-language batch test")
    args = parser.parse_args()

    if args.batch:
        test_batch()
    else:
        test_with_text(args.text, args.lang, args.speed)
