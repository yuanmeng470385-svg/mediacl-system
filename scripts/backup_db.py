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
    "OSS_ACCESS_KEY_ID": "",
    "OSS_ACCESS_KEY_SECRET": "",
    "OSS_BUCKET": "",
    "OSS_ENDPOINT": "",
}


def load_config() -> dict:
    """读取仓库根 .env 与默认值合并，环境变量优先级最高。

    合并规则：.env 中非空的键覆盖脚本默认值（空值行保留默认值 —— 如
    BACKUP_DIR= 空行不得把备份落到 cwd；A4 修复在此收紧）；环境变量（非空）
    再覆盖 .env，优先级最高。.env 中不在默认表的键（DATABASE_URL / DB_USER /
    DB_PASSWORD 等）也会并入 cfg 供下游使用。
    """
    cfg = dict(DEFAULT_CONFIG)
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip()
            # 空值行不覆盖非空默认值（如 BACKUP_DIR= 空行否则 Path("") 落到 cwd）
            if value:
                cfg[key] = value
    for key in list(cfg):
        env_val = os.getenv(key)
        if env_val:
            cfg[key] = env_val
    return cfg


def pg_password(cfg: dict) -> str:
    """备份口令：优先显式 DB_PASSWORD（独立账号环境），否则从 DATABASE_URL 解析。

    B6 修复（2026-08-12）：解析失败或仍回退默认值 medagent123 → fail（不再静默回退）。
    备份是 ECS cron 定时任务，静默用公开默认密码会掩盖凭据漏配（且默认密码本身是
    安全隐患）；本地开发豁免（AUTH_DEV_MODE/DEV_MODE=true，dev 库就是默认密码）。
    """
    explicit = cfg.get("DB_PASSWORD", "")
    if explicit:
        return explicit
    url = cfg.get("DATABASE_URL", "postgresql://medagent:medagent123@localhost:5432/medagent")
    m = re.search(r"postgres(?:ql)?://([^:]+):([^@]+)@", url)
    password = m.group(2) if m else ""
    if not password:
        raise RuntimeError(
            "DATABASE_URL 格式无法解析（应为 postgresql://user:pass@host:port/db）。"
            "请配置 DB_USER/DB_PASSWORD 或正确的 DATABASE_URL"
        )
    is_dev = (
        os.getenv("DEV_MODE", "").strip().lower() in ("1", "true", "yes", "on")
        or os.getenv("AUTH_DEV_MODE", "").strip().lower() in ("1", "true", "yes", "on")
    )
    if password == "medagent123" and not is_dev:
        raise RuntimeError(
            "DATABASE_URL 仍是默认密码 medagent123 —— 备份链路过期/漏配会被静默掩盖。"
            "请配置真实数据库凭据（DB_USER/DB_PASSWORD 或 DATABASE_URL）"
        )
    return password


def pg_user(cfg: dict) -> str:
    """备份/校验用的数据库用户：DB_USER 优先，缺省 medagent（与 pg_password 配套）。"""
    return cfg.get("DB_USER", "") or "medagent"


def log(msg: str, cfg: dict) -> None:
    """打印 + 追加写 logs/backup.log。"""
    line = f"{datetime.datetime.now().isoformat(timespec='seconds')} {msg}"
    print(line)
    log_dir = ROOT / "logs"
    log_dir.mkdir(exist_ok=True)
    with open(log_dir / "backup.log", "a", encoding="utf-8") as f:
        f.write(line + "\n")


def _oss_bucket(cfg: dict):
    """构造 oss2.Bucket（复用 .env 的 OSS_* 凭证）。凭证缺失/oss2 未装抛 RuntimeError。"""
    try:
        import oss2
    except ImportError:
        raise RuntimeError("oss2 未安装，请执行: pip install oss2")
    ak = cfg.get("OSS_ACCESS_KEY_ID", "")
    sk = cfg.get("OSS_ACCESS_KEY_SECRET", "")
    bucket_name = cfg.get("OSS_BUCKET", "")
    endpoint = cfg.get("OSS_ENDPOINT", "")
    if not (ak and sk and bucket_name and endpoint):
        raise RuntimeError(
            "未配置 OSS_ACCESS_KEY_ID/OSS_ACCESS_KEY_SECRET/OSS_BUCKET/OSS_ENDPOINT（见 .env.example）"
        )
    return oss2.Bucket(oss2.Auth(ak, sk), endpoint, bucket_name)


def upload_oss(cfg: dict, dump_path: Path) -> None:
    """上传 dump 到 OSS_BUCKET 的 BACKUP_OSS_PREFIX，ACL 显式私有。"""
    bucket = _oss_bucket(cfg)
    key = f"{cfg['BACKUP_OSS_PREFIX']}{dump_path.name}"
    bucket.put_object_from_file(key, str(dump_path), headers={"x-oss-object-acl": "private"})
    log(f"OSS 上传完成: {bucket.bucket_name}/{key}", cfg)


def cleanup_local(cfg: dict) -> int:
    """删除 BACKUP_DIR 中超过 BACKUP_RETENTION_LOCAL_DAYS 天的备份，返回删除数。"""
    days = int(cfg["BACKUP_RETENTION_LOCAL_DAYS"])
    cutoff = datetime.datetime.now() - datetime.timedelta(days=days)
    pattern = re.compile(r"^medagent-(\d{8})-\d{6}\.dump$")  # 秒级时间戳（B6 修复同步）
    removed = 0
    for p in Path(cfg["BACKUP_DIR"]).glob("medagent-*.dump"):
        m = pattern.match(p.name)
        if not m:
            continue
        file_date = datetime.datetime.strptime(m.group(1), "%Y%m%d")
        if file_date < cutoff:
            p.unlink(missing_ok=True)
            removed += 1
    if removed:
        log(f"本地清理: 删除 {removed} 个过期备份（>{days} 天）", cfg)
    return removed


def cleanup_oss(cfg: dict) -> int:
    """删除 OSS 中超过 BACKUP_RETENTION_OSS_DAYS 天的对象，返回删除数。"""
    try:
        import oss2
    except ImportError:
        raise RuntimeError("oss2 未安装，请执行: pip install oss2")
    days = int(cfg["BACKUP_RETENTION_OSS_DAYS"])
    cutoff = datetime.datetime.now() - datetime.timedelta(days=days)
    prefix = cfg["BACKUP_OSS_PREFIX"]
    bucket = _oss_bucket(cfg)
    pattern = re.compile(rf"^{re.escape(prefix)}medagent-(\d{{8}})-\d{{6}}\.dump$")  # 秒级时间戳（与 cleanup_local 一致）
    removed = 0
    for obj in oss2.ObjectIterator(bucket, prefix=prefix):
        m = pattern.match(obj.key)
        if not m:
            continue
        obj_date = datetime.datetime.strptime(m.group(1), "%Y%m%d")
        if obj_date < cutoff:
            bucket.delete_object(obj.key)
            removed += 1
    if removed:
        log(f"OSS 清理: 删除 {removed} 个过期对象（>{days} 天）", cfg)
    return removed


def run_pg_dump(cfg: dict) -> Path:
    """docker exec pg_dump -Fc 全量备份到 BACKUP_DIR。返回 dump 文件路径。"""
    dump_dir = Path(cfg["BACKUP_DIR"])
    dump_dir.mkdir(parents=True, exist_ok=True)
    # B6 修复（2026-08-12）：秒级时间戳 —— 分钟粒度下同分钟重跑会覆盖前一个 dump
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    dump_path = dump_dir / f"medagent-{stamp}.dump"
    # 二进制输出直写文件（不用 shell 重定向，防 Windows CRLF 破坏 custom 格式）
    with open(dump_path, "wb") as out:
        cmd = ["docker", "exec", "-e", f"PGPASSWORD={pg_password(cfg)}", cfg["BACKUP_PG_CONTAINER"],
               "pg_dump", "-U", pg_user(cfg), "-Fc", "medagent"]
        proc = subprocess.run(cmd, stdout=out, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        dump_path.unlink(missing_ok=True)
        raise RuntimeError(f"pg_dump 失败: {proc.stderr.decode('utf-8', 'replace')[:500]}")
    os.chmod(dump_path, 0o600)
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
        if not args.local_only:
            upload_oss(cfg, dump_path)   # 上传失败 → 异常中断，本地文件保留（7 天兜底）
        try:
            cleanup_local(cfg)
        except Exception as exc:
            log(f"本地清理失败（继续）: {exc}", cfg)
        if not args.local_only:
            try:
                cleanup_oss(cfg)
            except Exception as exc:
                log(f"OSS 清理失败（继续）: {exc}", cfg)
    except Exception as exc:
        log(f"备份失败: {exc}", cfg)
        (ROOT / "logs" / "backup-failed").touch()
        return 1
    (ROOT / "logs" / "backup-failed").unlink(missing_ok=True)
    log("备份全流程完成", cfg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
