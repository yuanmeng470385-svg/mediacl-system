"""上线挂账 §3（2026-09-14）：AUTH_DEV_MODE 生产守卫

背景：AUTH_DEV_MODE=true 时 send-code 在响应体里回传验证码，生产漏关等于
验证码裸奔。守卫（app/main.py 启动时）：DEV_MODE=true 且 DEPLOY_ENV=production
直接 RuntimeError 拒绝启动；dev 环境维持原有警告日志不动。

测法：子进程 import app.main（守卫在模块级执行），显式设置环境变量——
load_dotenv(override=False) 不会覆盖已设值，可挡住本机根 .env 的
AUTH_DEV_MODE=true 污染。
"""
import os
import subprocess
import sys

SERVICE_DIR = os.path.join(os.path.dirname(__file__), "..")
STRONG_JWT = "test-secret-not-a-default-value"


def _import_main_env(**overrides) -> dict:
    env = {k: v for k, v in os.environ.items() if k != "JWT_SECRET"}
    env.update(
        JWT_SECRET=STRONG_JWT,  # 先过 JWT 守卫，才能测到 DEV_MODE 守卫
        AUTH_DEV_MODE="false",
        DEPLOY_ENV="dev",
        # 绕开 shared B5 守卫（非 dev 环境默认库密码 fail-fast）：给个非默认密码的
        # 本地串即可，import 只建引擎不真连库
        DATABASE_URL="postgresql://medagent:test-db-password@localhost:5432/medagent",
    )
    env.update(overrides)
    return env


def _run_import(env: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", "import app.main"],
        cwd=SERVICE_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_dev_mode_in_production_refuses_to_start():
    """DEV_MODE=true + DEPLOY_ENV=production：import 即 RuntimeError 拒绝启动"""
    proc = _run_import(_import_main_env(AUTH_DEV_MODE="true", DEPLOY_ENV="production"))
    assert proc.returncode != 0
    assert "AUTH_DEV_MODE" in proc.stderr


def test_dev_mode_in_dev_env_still_boots():
    """DEV_MODE=true + DEPLOY_ENV=dev：本地联调形态，允许启动（仅警告）"""
    proc = _run_import(_import_main_env(AUTH_DEV_MODE="true", DEPLOY_ENV="dev"))
    assert proc.returncode == 0, proc.stderr


def test_production_without_dev_mode_boots():
    """DEV_MODE=false + DEPLOY_ENV=production：正常生产形态"""
    proc = _run_import(_import_main_env(AUTH_DEV_MODE="false", DEPLOY_ENV="production"))
    assert proc.returncode == 0, proc.stderr
