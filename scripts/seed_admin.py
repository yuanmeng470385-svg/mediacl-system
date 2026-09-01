#!/usr/bin/env python3
"""
设置/重置用户密码，并给出可用于登录的账号。

仓库里不放默认口令 —— init_db.sql 建的 admin 行 password_hash 为 NULL，
必须跑一次这个脚本才能用密码登录。

用法：
    # 给 admin 设置随机密码（打印一次，不落盘）
    python scripts/seed_admin.py

    # 指定密码
    python scripts/seed_admin.py --password 'Your-Strong-Pass'
    ADMIN_INIT_PASSWORD='Your-Strong-Pass' python scripts/seed_admin.py

    # 顺便设置手机号（手机号验证码登录需要）
    python scripts/seed_admin.py --phone 13812345678

    # 给别的用户设置
    python scripts/seed_admin.py --username zhangsan

前置：数据库已初始化（含 users.password_hash 列）。
      旧库先跑 scripts/migrations/001_add_user_password.sql
"""

import argparse
import os
import secrets
import string
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "services", "auth-service"))

from dotenv import load_dotenv

load_dotenv()

from shared.common.db_session import SessionLocal          # noqa: E402
from shared.models.user import User                        # noqa: E402
from app.core.security import hash_password                # noqa: E402

_ALPHABET = string.ascii_letters + string.digits + "!@#$%^&*-_"


def generate_password(length: int = 16) -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(length))


def main() -> int:
    parser = argparse.ArgumentParser(description="设置用户密码")
    parser.add_argument("--username", default="admin", help="目标用户名（默认 admin）")
    parser.add_argument("--password", default=None, help="明文密码；不传则读 ADMIN_INIT_PASSWORD，仍为空则随机生成")
    parser.add_argument("--phone", default=None, help="同时设置手机号（手机验证码登录用）")
    parser.add_argument("--create", action="store_true", help="用户不存在时自动创建（角色默认 admin，可用 --role 指定）")
    parser.add_argument("--role", default="admin", help="自动创建时的角色（admin/compliance/medical 等）")
    args = parser.parse_args()

    password = args.password or os.getenv("ADMIN_INIT_PASSWORD") or ""
    generated = False
    if not password:
        password = generate_password()
        generated = True

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == args.username).first()

        if not user:
            if not args.create:
                print(f"[失败] 用户 {args.username} 不存在。加 --create 可自动创建。")
                return 1
            user = User(
                username=args.username,
                full_name=args.username,
                role=args.role,
                status="active",
            )
            db.add(user)

        if args.phone:
            # 手机号唯一索引：先确认没被别人占用，避免报底层约束错误
            occupied = (
                db.query(User)
                .filter(User.phone == args.phone, User.username != args.username)
                .first()
            )
            if occupied:
                print(f"[失败] 手机号 {args.phone} 已被用户 {occupied.username} 占用。")
                return 1
            user.phone = args.phone

        user.password_hash = hash_password(password)
        db.commit()
        db.refresh(user)

        print("=" * 56)
        print("密码已设置")
        print("=" * 56)
        print(f"  用户名 : {user.username}")
        print(f"  手机号 : {user.phone or '（未设置，无法用验证码登录）'}")
        print(f"  角色   : {user.role}")
        if generated:
            print(f"  密码   : {password}")
            print("")
            print("  ↑ 随机生成，只显示这一次，请立刻存进密码管理器。")
        else:
            print("  密码   : （使用你提供的值，不回显）")
        print("=" * 56)
        print("验证登录：")
        print(f'  curl -X POST http://localhost:8000/api/v1/auth/login \\')
        print(f'    -H "Content-Type: application/json" \\')
        print(f'    -d \'{{"username":"{user.username}","password":"<上面的密码>"}}\'')
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
