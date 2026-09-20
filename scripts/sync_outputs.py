"""将 git 仓库的对外产物同步到 OUTPUTS 交付目录。

OUTPUTS（默认 ``F:\\BPI\\OUTPUTS``）是本仓库的对外交付镜像。本脚本刷新其中同步的
三个子目录（paper / artifacts / reproducibility），并保留上一轮的过程/归档记录
（audits/、github_release_*、structure_migration_*、data_archive_*）不动。

用法：
  python scripts/sync_outputs.py               # 同步到默认 OUTPUTS
  python scripts/sync_outputs.py --out DIR     # 同步到自定义目录
"""
import argparse
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO.parents[1] / "OUTPUTS"

# 需要同步的仓库子目录（整目录复制）
SYNC_DIRS = ("paper", "artifacts", "reproducibility")

# paper 下的编译中间件不进入对外产物
PAPER_IGNORE = {"main.aux", "main.bbl", "main.blg", "main.log", "main.out"}


def _ignore_paper(_dirpath: str, names: list[str]) -> list[str]:
    return [n for n in names if n in PAPER_IGNORE]


def sync(out: Path) -> None:
    for d in SYNC_DIRS:
        target = out / d
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(REPO / d, target, ignore=_ignore_paper if d == "paper" else None)
        print(f"synced {d}/ -> {target}")
    print("done")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="目标 OUTPUTS 目录")
    args = parser.parse_args(argv)
    sync(Path(args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
