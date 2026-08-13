#!/usr/bin/env python3
"""MedAgent 数据库恢复：把备份 dump 恢复到临时库验证可恢复性（默认不碰生产库）。

用法：
    python scripts/restore_db.py --source local             # 本地最近一份
    python scripts/restore_db.py --source local --dump backups/medagent-20260812-0200.dump
    python scripts/restore_db.py --source oss               # 从 OSS 下载最近一份
    python scripts/restore_db.py --source local --target-db medagent_restore --yes

配置同 backup_db.py（复用 load_config）。
恢复默认到 medagent_restore 临时库，绝不自动覆盖生产库；覆盖需显式 --yes。
恢复生产库的步骤（人执行，勿自动化）：
    1) 停所有服务（docker compose -f deploy/docker-compose.prod.yml stop）
    2) docker exec medagent-postgres psql -U medagent -c "DROP DATABASE medagent WITH (FORCE)"
    3) python scripts/restore_db.py --source oss --target-db medagent --yes
    4) 重启服务；审计不可篡改配置（002 迁移）需在新库重新执行
"""
import argparse
import datetime
import re
import subprocess
import sys
from pathlib import Path

from backup_db import load_config, log, pg_password, _oss_bucket, ROOT

BACKUP_DIR = Path(load_config()["BACKUP_DIR"])


def _psql(cfg: dict, db: str, sql: str) -> subprocess.CompletedProcess:
    """docker exec psql 执行单条 SQL，返回 CompletedProcess。"""
    cmd = ["docker", "exec", "-e", f"PGPASSWORD={pg_password(cfg)}", cfg["BACKUP_PG_CONTAINER"],
           "psql", "-U", "medagent", "-d", db, "-t", "-A", "-c", sql]
    return subprocess.run(cmd, capture_output=True)


def pick_dump(cfg: dict, source: str, dump_arg: str | None) -> Path:
    """定位 dump 文件：本地按 --dump 或取最近一份；OSS 下载最近一份到 BACKUP_DIR/restore/。"""
    if source == "local":
        if dump_arg:
            p = Path(dump_arg)
            if not p.exists():
                raise RuntimeError(f"dump 文件不存在: {dump_arg}")
            return p
        dumps = sorted(BACKUP_DIR.glob("medagent-*.dump"))
        if not dumps:
            raise RuntimeError(f"{cfg['BACKUP_DIR']} 下没有备份文件")
        return dumps[-1]
    # OSS：对象 key 按字典序 = 时间序，取最近一份
    try:
        import oss2
    except ImportError:
        raise RuntimeError("oss2 未安装，请执行: pip install oss2")
    bucket = _oss_bucket(cfg)
    prefix = cfg["BACKUP_OSS_PREFIX"]
    pattern = re.compile(rf"^{re.escape(prefix)}medagent-(\d{{8}})-\d{{6}}\.dump$")  # 秒级时间戳（B6 同步）
    objs = [o for o in oss2.ObjectIterator(bucket, prefix=prefix) if pattern.match(o.key)]
    if not objs:
        raise RuntimeError("OSS 上没有备份对象")
    latest = sorted(objs, key=lambda o: o.key)[-1]
    restore_dir = BACKUP_DIR / "restore"
    restore_dir.mkdir(parents=True, exist_ok=True)
    target = restore_dir / latest.key.rsplit("/", 1)[-1]
    bucket.get_object_to_file(latest.key, str(target))
    log(f"OSS 下载完成: {latest.key}", cfg)
    return target


def ensure_target_db(cfg: dict, target_db: str, yes: bool) -> None:
    """目标库已存在时要求确认（--yes 跳过）后 drop 重建，owner 为 medagent。"""
    proc = _psql(cfg, "postgres", f"SELECT 1 FROM pg_database WHERE datname='{target_db}'")
    if proc.returncode != 0:
        raise RuntimeError(f"检查目标库失败: {proc.stderr.decode('utf-8', 'replace')[:300]}")
    exists = proc.stdout.decode("utf-8", "replace").strip() == "1"
    if exists:
        if not yes:
            answer = input(f"目标库 {target_db} 已存在，drop 重建？[y/N] ")
            if answer.strip().lower() != "y":
                raise RuntimeError("已取消")
        proc = _psql(cfg, "postgres", f"DROP DATABASE {target_db} WITH (FORCE)")
        if proc.returncode != 0:
            raise RuntimeError(f"drop 目标库失败: {proc.stderr.decode('utf-8', 'replace')[:300]}")
    proc = _psql(cfg, "postgres", f"CREATE DATABASE {target_db} OWNER medagent")
    if proc.returncode != 0:
        raise RuntimeError(f"创建目标库失败: {proc.stderr.decode('utf-8', 'replace')[:300]}")


def restore_dump(cfg: dict, dump_path: Path, target_db: str) -> None:
    """pg_restore --no-owner --no-privileges 灌入目标库（stdin 喂 dump 字节）。

    B6 修复（2026-08-12）：加 --exit-on-error —— pg_restore 默认遇到错误只告警
    继续，部分恢复失败也会返回 0，让"恢复完成"变成假成功（后续行数校验才暴露）。
    """
    with open(dump_path, "rb") as f:
        cmd = ["docker", "exec", "-i", "-e", f"PGPASSWORD={pg_password(cfg)}", cfg["BACKUP_PG_CONTAINER"],
               "pg_restore", "--no-owner", "--no-privileges", "--exit-on-error",
               "-U", "medagent", "-d", target_db]
        proc = subprocess.run(cmd, stdin=f, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(f"pg_restore 失败: {proc.stderr.decode('utf-8', 'replace')[:500]}")


def _query_counts(cfg: dict, db: str, tables: tuple) -> dict:
    """返回 {表名: 行数}。"""
    sql = " UNION ALL ".join(f"SELECT '{t}', COUNT(*) FROM {t}" for t in tables)
    proc = _psql(cfg, db, sql)
    if proc.returncode != 0:
        raise RuntimeError(f"查询 {db} 行数失败: {proc.stderr.decode('utf-8', 'replace')[:300]}")
    counts = {}
    for line in proc.stdout.decode("utf-8", "replace").splitlines():
        if "|" in line:
            t, _, n = line.partition("|")
            counts[t.strip()] = int(n.strip())
    return counts


def verify_counts(cfg: dict, src_db: str, target_db: str,
                  tables: tuple = ("users", "conversations", "audit_logs")) -> dict:
    """对比源库与目标库行数，返回 (src, tgt, mismatches)。"""
    src = _query_counts(cfg, src_db, tables)
    tgt = _query_counts(cfg, target_db, tables)
    mismatches = {t: (src.get(t), tgt.get(t)) for t in tables if src.get(t) != tgt.get(t)}
    return {"source": src, "target": tgt, "mismatches": mismatches}


def main() -> int:
    parser = argparse.ArgumentParser(description="MedAgent 数据库恢复（默认恢复临时库）")
    parser.add_argument("--source", choices=["local", "oss"], default="local", help="备份来源")
    parser.add_argument("--dump", default=None, help="指定 dump 文件（默认取最近一份）")
    parser.add_argument("--target-db", default="medagent_restore", help="恢复目标库（默认临时库）")
    parser.add_argument("--yes", action="store_true", help="目标库已存在时跳过确认直接重建")
    args = parser.parse_args()
    cfg = load_config()
    try:
        if not re.fullmatch(r"[A-Za-z0-9_]+", args.target_db):
            raise RuntimeError(f"目标库名非法（仅允许字母/数字/下划线）: {args.target_db}")
        dump_path = pick_dump(cfg, args.source, args.dump)
        ensure_target_db(cfg, args.target_db, args.yes)
        restore_dump(cfg, dump_path, args.target_db)
        result = verify_counts(cfg, "medagent", args.target_db)
    except Exception as exc:
        log(f"恢复失败: {exc}", cfg)
        return 1
    print(f"恢复完成: {dump_path} → {args.target_db}")
    print(f"源库行数: {result['source']}")
    print(f"目标库行数: {result['target']}")
    if result["mismatches"]:
        log(f"恢复校验不一致: {result['mismatches']}", cfg)
        return 1
    log(f"恢复验证通过: {dump_path.name} → {args.target_db} 行数一致", cfg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
