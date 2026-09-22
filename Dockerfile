# SkillGap Agent 应用镜像（ADR-012：单阶段 python:3.12-slim + 非 root）
# 安装方式裁决（Phase 11 T2 方案 A）：editable 安装——db.py 的 MIGRATIONS_DIR
# 按 __file__ 上三级定位源码树，非 editable 安装进 site-packages 后 migrations
# 不可见（db-upgrade 会 glob 到空、静默跳过全部迁移）；源码 COPY 到 /app 后
# migrations / data 等相对路径与开发态完全一致。
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# 非 root 运行（ADR-012 D1）
RUN useradd --create-home --uid 1000 skillgap

WORKDIR /app

COPY pyproject.toml ./
COPY src/ src/
COPY migrations/ migrations/
COPY data/ data/

RUN pip install --no-cache-dir -e .

COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod 0555 /usr/local/bin/entrypoint.sh

USER skillgap
EXPOSE 8000
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
