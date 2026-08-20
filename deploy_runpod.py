#!/usr/bin/env python3
"""
RunPod Serverless 部署脚本（GraphQL API）
==========================================
创建 Template + Endpoint，使用 RunPod 官方 API（无需打开网页控制台）。

用法：
    export RUNPOD_API_KEY="rpa_..."        # 你的 RunPod API 密钥
    export IMAGE="ghcr.io/ber1205/indextts-2-5:latest"
    python deploy_runpod.py

可选环境变量：
    ENDPOINT_NAME  默认 indextts-2-5
    GPU_ID         默认 "NVIDIA RTX 4000 Ada Generation"
    WORKERS_MIN    默认 0（无请求 0 实例 0 计费）
    WORKERS_MAX    默认 2
    IDLE_TIMEOUT   默认 300（秒，5 分钟无请求自动缩到 0）
    SCALE_TIMEOUT  默认 600（秒，冷启动最长等待）
"""
import json
import os
import sys
import time
import urllib.request

API = "https://api.runpod.io/graphql"
API_KEY = os.environ.get("RUNPOD_API_KEY", "")
if not API_KEY:
    sys.exit("缺少环境变量 RUNPOD_API_KEY")

IMAGE = os.environ.get("IMAGE", "ghcr.io/ber1205/indextts-2-5:latest")
ENDPOINT_NAME = os.environ.get("ENDPOINT_NAME", "indextts-2-5")
GPU_ID = os.environ.get("GPU_ID", "NVIDIA RTX 4000 Ada Generation")
WORKERS_MIN = int(os.environ.get("WORKERS_MIN", "0"))
WORKERS_MAX = int(os.environ.get("WORKERS_MAX", "2"))
IDLE_TIMEOUT = int(os.environ.get("IDLE_TIMEOUT", "300"))
SCALE_TIMEOUT = int(os.environ.get("SCALE_TIMEOUT", "600"))


def gql(query: str, variables: dict = None) -> dict:
    body = json.dumps({"query": query, "variables": variables or {}}).encode()
    req = urllib.request.Request(
        API, data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


def main():
    print(f">> IMAGE       = {IMAGE}")
    print(f">> ENDPOINT    = {ENDPOINT_NAME}")
    print(f">> GPU         = {GPU_ID}")
    print(f">> Workers     = min {WORKERS_MIN} / max {WORKERS_MAX}")
    print(f">> Idle/Scale  = {IDLE_TIMEOUT}s / {SCALE_TIMEOUT}s")

    # 1) 创建 Template
    tpl = gql("""
      mutation createTemplate($input: TemplateInput!) {
        createTemplate(input: $input) { id name }
      }
    """, {"input": {
        "name": ENDPOINT_NAME,
        "image": IMAGE,
        "dockerStartCommand": "python -u /app/index-tts/handler.py",
        "containerDiskInGb": 40,
        "isServerless": True,
        "envs": [{"key": "PRELOAD", "value": "1"}],
    }})
    tpl_data = tpl.get("data", {}).get("createTemplate")
    if not tpl_data:
        print("!! createTemplate 返回:", json.dumps(tpl, ensure_ascii=False))
        sys.exit(1)
    template_id = tpl_data["id"]
    print(f">> Template 已创建: id={template_id} name={tpl_data['name']}")

    # 2) 创建 Endpoint
    ep = gql("""
      mutation createEndpoint($input: EndpointInput!) {
        createEndpoint(input: $input) { id name gpuIds workersMin workersMax idleTimeout scaleTimeout }
      }
    """, {"input": {
        "name": ENDPOINT_NAME,
        "templateId": template_id,
        "gpuIds": GPU_ID,
        "workersMin": WORKERS_MIN,
        "workersMax": WORKERS_MAX,
        "idleTimeout": IDLE_TIMEOUT,
        "scaleTimeout": SCALE_TIMEOUT,
        "networkVolumeId": None,
    }})
    ep_data = ep.get("data", {}).get("createEndpoint")
    if not ep_data:
        print("!! createEndpoint 返回:", json.dumps(ep, ensure_ascii=False))
        sys.exit(1)
    print(">> Endpoint 已创建:")
    print("   ", json.dumps(ep_data, ensure_ascii=False))
    print()
    print(f">> 调用地址（RunPod API）: https://api.runpod.ai/v2/{ENDPOINT_NAME}/runsync")
    print(f">> 调用地址（RunPod HTTP）: https://{ENDPOINT_NAME}-{ep_data['id']}.runpod.ai")
    print(f">> 首次调用会冷启动（拉镜像+加载模型约 2-5 分钟），之后 1-3 秒响应。")


if __name__ == "__main__":
    main()
