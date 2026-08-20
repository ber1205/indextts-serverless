# 探针 Dockerfile：仅验证 CUDA 基础镜像可拉取 + 构建器正常（不含大文件）
FROM nvidia/cuda:12.8.1-devel-ubuntu22.04
RUN echo "base image OK" && nvcc --version | tail -1
