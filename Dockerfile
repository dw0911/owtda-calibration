# OW-TDA-CAL-R1 — 可复现环境（Level 1/2 用；Level 3 需挂载算力与账本）
# 构建：docker build -t owtda-calibration .
# 验证：docker run --rm owtda-calibration
# 交互：docker run --rm -it owtda-calibration bash

FROM python:3.12-slim

# 冻结运行约定：线程变量=1（与正式结果一致）
ENV PYTHONDONTWRITEBYTECODE=1 \
    OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    NUMEXPR_NUM_THREADS=1 \
    UV_LINK_MODE=copy

WORKDIR /repo

# uv（版本固定在镜像层里，锁文件决定依赖）
RUN pip install --no-cache-dir "uv==0.12.12"

# 只拷贝锁定的依赖描述，最大化缓存命中
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

# 其余内容
COPY . .
RUN uv sync --frozen

# 默认动作：Level 1 快速验证 + 冒烟（不开 Monte Carlo）
CMD ["sh", "-c", "uv run python scripts/verify_release.py --level quick && uv run python scripts/run_smoke.py"]
