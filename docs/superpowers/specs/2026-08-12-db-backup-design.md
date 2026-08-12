# 数据库自动备份设计

日期：2026-08-12
状态：已确认（用户拍板：ECS 本地 + OSS / 每日 1 次 / 自动校验 + 恢复脚本）

## 背景

MedAgent 全部业务数据（账户、对话记录、拜访记录、收藏、医生档案、审计日志）存于 Docker 容器 `medagent-postgres` 的 named volume `postgres_data`，**目前没有任何备份机制**——ECS 服务器磁盘损坏或误删即数据全丢。本设计为 PostgreSQL 增加自动备份 + 异地存储 + 可恢复验证。

## 决策

- **方案 B：Python 脚本**（`scripts/backup_db.py` + `scripts/restore_db.py`，oss2 SDK 上传）——与项目现有 scripts/ 工具风格一致（seed_admin.py / smoke_runbook.py / arms-monitor.py），Windows 开发机与 Linux ECS 均可运行，本机 docker 即可验证全链路
- 否决：纯 bash + ossutil（不跨平台，本机无法验证）；RDS 托管（002 审计不可篡改迁移依赖 `postgres --single` 单用户模式，RDS 无法执行，会破坏审计方案）

## 组件

### scripts/backup_db.py — 备份主脚本

数据流：

```
ECS crontab（每天 02:00）
   └─ python scripts/backup_db.py
        ├─ docker exec medagent-postgres pg_dump -U medagent -Fc medagent
        │    → BACKUP_DIR/medagent-YYYYMMDD-HHMM.dump（custom 格式，自带压缩）
        ├─ 校验：pg_restore --list 能解析 + 文件非零大小
        │    └─ 校验失败 → 不传 OSS、ARMS 上报失败、退出码 1
        ├─ oss2 上传 → OSS_BUCKET 的 backups/medagent-YYYYMMDD.dump（私有 ACL）
        ├─ 过期清理：本地 >7 天删除；OSS >30 天删除（按日期前缀）
        └─ 全成功 → 日志 + 退出码 0
```

- 备份账号：`medagent`（002 迁移降级后仍有全表 SELECT，无需 superuser）
- 容器名 `medagent-postgres` 可经 `BACKUP_PG_CONTAINER` 配置（默认同名）
- 文件名时间戳精确到分钟，同一天多次运行不覆盖

### scripts/restore_db.py — 恢复脚本

- 用法：`python scripts/restore_db.py --source local|oss [--dump 文件|--latest]`
- **默认恢复到新临时库 `medagent_restore`，绝不直接覆盖生产库**
- 流程：建临时库 → `pg_restore --no-owner` 灌入 → 校验关键表行数（users / conversations / audit_logs）对比源库 → 输出报告
- 恢复生产库的完整步骤（停服务 → 灌库 → 启服务）写入脚本 --help 与 CLAUDE.md，由人执行

### 调度

ECS 上 crontab 配置（写入 README 部署段与 CLAUDE.md）：

```bash
# 每天 02:00 备份（ECS 时区 CST）
0 2 * * * cd /opt/medagent && python scripts/backup_db.py >> logs/backup.log 2>&1
```

### 配置（.env 新增，复用现有 OSS_* 凭证）

```
BACKUP_DIR=./backups                # 本地保留目录（加入 .gitignore）
BACKUP_RETENTION_LOCAL_DAYS=7
BACKUP_RETENTION_OSS_DAYS=30
BACKUP_OSS_PREFIX=backups/          # OSS 对象前缀
BACKUP_PG_CONTAINER=medagent-postgres
```

依赖：`oss2`（阿里云官方 Python SDK；docstring 写明 `pip install oss2`，import 失败时打印安装指引并退出非零）。

## 错误处理（安全方向）

| 失败点 | 行为 |
|--------|------|
| 容器不可达 / pg_dump 失败 | 立即失败 + 日志 + ARMS 上报，退出码 1 |
| dump 校验失败 | **不上传 OSS**（OSS 保留的始终是可恢复的备份）+ ARMS 上报 |
| OSS 上传失败 | 保留本地文件（本地 7 天仍在），ARMS 上报 |
| 本地清理失败 | 只警告不中断（磁盘满时保留文件是安全方向） |
| oss2 未安装 | 打印安装指引，退出码 1 |

告警：复用阿里云 ARMS 上报模式（`deploy/arms-monitor.py` 已有 HMAC 签名先例）；未配置 AK/SK 时打印指引并退出非零（不假装成功）。备份成功可不上报，仅失败上报，避免噪声。

## 恢复流程（restore_db.py）

```
1. 解析参数（--source local|oss，--dump 指定文件或 --latest 取最近一份）
2. 连接 postgres（docker exec psql，本机/ECS 同路径）
3. 目标库 medagent_restore 已存在 → 明确确认后 drop 重建（不自动删）
4. pg_restore --no-owner --no-privileges -d medagent_restore <dump>
   （--no-owner：audit_logs 的 owner 是 NOLOGIN 占位角色 medagent_audit_owner，
    新环境该角色不一定存在，跳过所有权与权限恢复）
5. 校验：users / conversations / audit_logs 行数与源库对比，输出报告
6. 退出码：全过 0，任何失败非零
```

## 测试策略（本机全链路真实验证，本机 docker 即有 postgres）

1. 本机跑 `backup_db.py` → 生成 dump → 校验通过
2. `restore_db.py --source local` 恢复到临时库 → 关键表行数与源库一致
3. OSS 真实上传一次 → oss2 列对象确认 → 删除测试对象
4. 损坏文件校验路径：截断 dump 文件，确认校验能拦住（不上传、退出非零）

## 边界与说明

- **Redis 不备份**：缓存数据（验证码/限流/token），丢失自动重建，不影响业务数据
- 备份含患者对话与审计数据：OSS 对象 ACL 私有（oss2 默认私有）；本地文件权限 Linux chmod 600
- `.gitignore` 增补 `backups/`
- CLAUDE.md 增补「备份/恢复」小节（命令、配置、cron、恢复步骤）；README 部署段补 cron 配置
- 审计表 002 迁移约束：dump 时 `medagent` 账号权限已足够（表级 SELECT）；恢复跳过 owner 后，新库的审计不可篡改配置需重新执行 002 迁移（写入恢复文档注意事项）
