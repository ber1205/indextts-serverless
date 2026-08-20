# 探针：验证最小 CUDA base 镜像可拉取构建
FROM nvidia/cuda:12.8.1-base-ubuntu22.04
RUN echo "base image OK" && cat /usr/local/cuda/version.json 2>/dev/null | head -5 || echo "cuda present"
