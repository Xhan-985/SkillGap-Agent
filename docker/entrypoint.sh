#!/bin/sh
# ADR-012 D3：db-upgrade → seed → serve（全幂等，重启安全；迁移失败 fail-fast 退出）
set -e

echo "[entrypoint] db-upgrade：应用未执行的迁移..."
skillgap db-upgrade

echo "[entrypoint] seed：词表 v1 + 来源注册表建档（幂等）..."
skillgap seed

echo "[entrypoint] serve：启动 API / Dashboard..."
# 容器内绑 0.0.0.0（容器网络内可达）——本地单用户红线由 compose 端口映射
# "127.0.0.1:8000:8000" 在宿主侧强制（API.md §0 / ADR-012 D2）
exec skillgap serve --host 0.0.0.0 --port "${PORT:-8000}"
