#!/usr/bin/env python3
"""MedAgent 数据库备份：pg_dump -Fc 全量备份 + 完整性校验。

用法：
    python scripts/backup_db.py               # 备份 + 校验 + 上传 OSS + 过期清理
    python scripts/backup_db.py --local-only  # 只备份本地 + 校验（不上传 OSS）

配置（自动读取仓库根 .env，环境变量优先）：
    BACKUP_DIR                  本地保留目录（默认 ./backups）
    BACKUP_RETENTION_LOCAL_DAYS 本地保留天数（默认 7）
    BACKUP_RETENTION_OSS_DAYS   OSS 保留天数（默认 30）
    BACKUP_OSS_PREFIX           OSS 对象前缀（默认 backups/）
    BACKUP_PG_CONTAINER         数据库容器名（默认 medagent-postgres）
    OSS_ACCESS_KEY_ID / OSS_ACCESS_KEY_SECRET / OSS_BUCKET / OSS_ENDPOINT

依赖：oss2（pip install oss2），仅 OSS 上传/下载路径需要。
失败处理：logs/backup.log 追加日志 + logs/backup-failed 标记文件 + 非零退出码。
"""
import argparse
import datetime
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

DEFAULT_CONFIG = {
    "BACKUP_DIR": "./backups",
    "BACKUP_RETENTION_LOCAL_DAYS": "7",
    "BACKUP_RETENTION_OSS_DAYS": "30",
    "BACKUP_OSS_PREFIX": "backups/",
    "BACKUP_PG_CONTAINER": "medagent-postgres",
}


def load_config() -> dict:
    """读取仓库根 .env（若存在且环境未设置则补充），返回配置 dict。"""
    cfg = dict(DEFAULT_CONFIG)
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            cfg.setdefault(key.strip(), value.strip())
    for key in list(cfg):
        env_val = os.getenv(key)
        if env_val:
            cfg[key] = env_val
    return cfg


def pg_password(cfg: dict) -> str:
    """从 .env 的 DATABASE_URL 解析密码（缺省 dev compose 的 medagent123）。"""
    url = cfg.get("DATABASE_URL", "postgresql://medagent:medagent123@localhost:5432/medagent")
    m = re.search(r"postgres(?:ql)?://([^:]+):([^@]+)@", url)
    return m.group(2) if m else "medagent123"


def log(msg: str, cfg: dict) -> None:
    """打印 + 追加写 logs/backup.log。"""
    line = f"{datetime.datetime.now().isoformat(timespec='seconds')} {msg}"
    print(line)
    log_dir = ROOT / "logs"
    log_dir.mkdir(exist_ok=True)
    with open(log_dir / "backup.log", "a", encoding="utf-8") as f:
        f.write(line + "\n")


def _docker_exec(cfg: dict, args: list, input_bytes: bytes | None = None) -> subprocess.CompletedProcess:
    """docker exec 进 postgres 容器执行命令（带 PGPASSWORD）。"""
    cmd = ["docker", "exec", "-e", f"PGPASSWORD={pg_password(cfg)}", cfg["BACKUP_PG_CONTAINER"], *args]
    return subprocess.run(cmd, input=input_bytes, capture_output=True)


def run_pg_dump(cfg: dict) -> Path:
    """docker exec pg_dump -Fc 全量备份到 BACKUP_DIR。返回 dump 文件路径。"""
    dump_dir = Path(cfg["BACKUP_DIR"])
    dump_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M")
    dump_path = dump_dir / f"medagent-{stamp}.dump"
    # 二进制输出直写文件（不用 shell 重定向，防 Windows CRLF 破坏 custom 格式）
    with open(dump_path, "wb") as out:
        cmd = ["docker", "exec", "-e", f"PGPASSWORD={pg_password(cfg)}", cfg["BACKUP_PG_CONTAINER"],
               "pg_dump", "-U", "medagent", "-Fc", "medagent"]
        proc = subprocess.run(cmd, stdout=out, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        dump_path.unlink(missing_ok=True)
        raise RuntimeError(f"pg_dump 失败: {proc.stderr.decode('utf-8', 'replace')[:500]}")
    return dump_path


def validate_dump(dump_path: Path, cfg: dict) -> None:
    """pg_restore --list 校验 dump 可解析 + 文件非零。失败抛 RuntimeError。"""
    if dump_path.stat().st_size == 0:
        raise RuntimeError(f"dump 文件为空: {dump_path}")
    with open(dump_path, "rb") as f:
        cmd = ["docker", "exec", "-i", "-e", f"PGPASSWORD={pg_password(cfg)}", cfg["BACKUP_PG_CONTAINER"],
               "pg_restore", "--list"]
        proc = subprocess.run(cmd, stdin=f, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        raise RuntimeError(f"dump 校验失败（pg_restore --list 非零）: {proc.stderr.decode('utf-8', 'replace')[:500]}")


def main() -> int:
    parser = argparse.ArgumentParser(description="MedAgent 数据库备份")
    parser.add_argument("--local-only", action="store_true", help="只做本地备份+校验，不上传 OSS（开发环境用）")
    args = parser.parse_args()
    cfg = load_config()
    try:
        dump_path = run_pg_dump(cfg)
        validate_dump(dump_path, cfg)
    except Exception as exc:
        log(f"备份失败: {exc}", cfg)
        (ROOT / "logs" / "backup-failed").touch()
        return 1
    log(f"备份完成: {dump_path.name}（--local-only={'是' if args.local_only else '否'}）", cfg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
