#!/usr/bin/env bash
# ===========================================================================
# 在你自己的电脑上执行：构建镜像 + 推送 GHCR（唯一需要你做的步骤）
# 要求：已安装 Docker（无需 GPU，普通电脑即可），约 30-50 分钟、40GB 磁盘
# 中国大陆网络：构建前执行  export HF_ENDPOINT=https://hf-mirror.com
# ===========================================================================
set -euo pipefail

GHCR_USER="ber1205"          # 已从你的 GitHub Token 验证
IMAGE="ghcr.io/${GHCR_USER}/indextts-2-5:latest"

echo "==> [1/4] 登录 GHCR"
echo "${GHCR_TOKEN:-}" | docker login ghcr.io -u "${GHCR_USER}" --password-stdin

echo "==> [2/4] 构建镜像（官方代码 + 全量权重，耐心等待）"
docker build --progress=plain -t "${IMAGE}" .

echo "==> [3/4] 推送镜像"
docker push "${IMAGE}"

echo "==> [4/4] 完成: ${IMAGE}"
echo "接下来把镜像地址发给 AI：${IMAGE}"
