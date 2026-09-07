#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""一键拉起 / 体检本机 MedAgent 演示环境（Windows；git-bash / PowerShell 均可）。

项目长期在本机运行和演示（见 CLAUDE.md），本脚本固化日常拉起流程，幂等可重跑：
Docker Desktop → postgres/redis → 8 个 uvicorn 服务 → （可选）种子 / 模拟器 / Metro / 双端 App。

用法：
  python scripts/dev_up.py            # 拉起缺的（docker/DB/8服务），健康检查收尾
  python scripts/dev_up.py --check    # 只体检不启动任何东西（演示前快速核对）
  python scripts/dev_up.py --seed     # 在默认流程后追加 seed_demo_data.py（幂等）
  python scripts/dev_up.py --app      # 追加：模拟器 Pixel_7 + Metro 8081/8082 + 双端 App
  python scripts/dev_up.py --down     # 停 8 个 uvicorn 服务（不动 docker / 模拟器 / Metro）

注意：
  - 服务启动用独立进程（CREATE_NO_WINDOW），日志在 logs/native/<服务名>.log；
    audit-service 启动时报 audit 日志清理 InsufficientPrivilege 属预期（002 防篡改 owner 分离）。
  - 模拟器走 10.0.2.2（config.ts 模拟器态）或宿主局域网 IP（真机态）均可，
    换网络后 --check 会核对 config.ts 与本机当前 IP。
"""
import argparse
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT / "logs" / "native"
CREATE_NO_WINDOW = 0x08000000

# (目录名, 端口) —— 目录名即 services/ 下文件夹名，也是日志文件名
SERVICES = [
    ("gateway", 8000),
    ("specialist-service", 8001),
    ("visit-service", 8002),
    ("knowledge-service", 8003),
    ("compliance-service", 8004),
    ("audit-service", 8005),
    ("hcp-service", 8006),
    ("auth-service", 8007),
]
APPS = {  # 模拟器上的两个 App（包名 → metro 端口；医生端 dev 构建连 8082，别改）
    "com.medagent.mobile": 8081,
    "com.medagent.doctor": 8082,
}
METRO_PORTS = {8081: ROOT / "mobile", 8082: ROOT / "mobile-doctor"}
DOCKER_DESKTOP = Path(r"C:\Program Files\Docker\Docker\Docker Desktop.exe")
EMULATOR = Path(r"D:\AndroidSDK\emulator\emulator.exe")
ADB = shutil.which("adb") or r"D:\AndroidSDK\platform-tools\adb.exe"


def ok(msg):
    print(f"  [OK]   {msg}")


def warn(msg):
    print(f"  [WARN] {msg}")


def fail(msg):
    print(f"  [FAIL] {msg}")


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", **kw)


# ---------- 基础探测 ----------

def port_listening(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def http_ok(port: int, path: str = "/health", timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def local_ip() -> str | None:
    """本机当前局域网出口 IP（不实际发包；多网卡时取默认路由那张）"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
    except Exception:
        return None


def psql(sql: str) -> str | None:
    r = run(["docker", "exec", "medagent-postgres", "psql", "-U", "medagent",
             "medagent", "-A", "-t", "-c", sql])
    return r.stdout.strip() if r.returncode == 0 else None


# ---------- Docker / 数据库 ----------

def ensure_docker(wait_s: int = 240):
    if run(["docker", "ps"]).returncode == 0:
        ok("Docker 已在运行")
        return True
    if not DOCKER_DESKTOP.exists():
        fail(f"docker 不可用且未找到 Docker Desktop：{DOCKER_DESKTOP}")
        return False
    print("  ... 启动 Docker Desktop（WSL 引擎，首次约 1-3 分钟）")
    subprocess.Popen([str(DOCKER_DESKTOP)], creationflags=CREATE_NO_WINDOW)
    t0 = time.time()
    while time.time() - t0 < wait_s:
        if run(["docker", "ps"]).returncode == 0:
            ok(f"Docker 就绪（{int(time.time() - t0)}s）")
            return True
        time.sleep(5)
    fail("Docker 等待超时——手动开 Docker Desktop 后重跑")
    return False


def ensure_db():
    r = run(["docker", "ps", "--format", "{{.Names}} {{.Status}}"])
    up = r.stdout or ""
    if "medagent-postgres" in up and "medagent-redis" in up:
        ok(f"postgres/redis 容器已在运行")
        return True
    print("  ... docker-compose up -d postgres redis")
    r = run(["docker-compose", "up", "-d", "postgres", "redis"], cwd=str(ROOT))
    if r.returncode != 0:
        fail(f"容器启动失败：{(r.stderr or r.stdout).strip()[:200]}")
        return False
    for _ in range(20):  # 等 postgres healthy
        h = run(["docker", "inspect", "-f", "{{.State.Health.Status}}", "medagent-postgres"])
        if h.stdout.strip() == "healthy":
            break
        time.sleep(2)
    ok("postgres/redis 容器已起")
    return True


# ---------- 后端服务 ----------

def ensure_services() -> bool:
    all_ok = True
    for name, port in SERVICES:
        if http_ok(port):
            ok(f"{name}(:{port}) 健康")
            continue
        if port_listening(port):
            warn(f"{name}(:{port}) 端口在监听但 /health 不通（可能还在启动，或挂的不是它）")
            continue
        log = LOG_DIR / f"{name}.log"
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with open(log, "a", encoding="utf-8") as f:
            subprocess.Popen(
                [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", str(port)],
                cwd=str(ROOT / "services" / name), stdout=f, stderr=subprocess.STDOUT,
                creationflags=CREATE_NO_WINDOW,
            )
        good = False
        t0 = time.time()
        while time.time() - t0 < 60:  # 冷启动（--down 后）gateway 导入+启动检查慢，40s 不够
            time.sleep(2)
            if http_ok(port):
                good = True
                break
        if good:
            ok(f"{name}(:{port}) 已拉起")
        elif port_listening(port):
            warn(f"{name}(:{port}) 端口已监听但 /health 未就绪（启动慢，稍后 --check 复核）")
        else:
            fail(f"{name}(:{port}) 启动失败，看 {log}")
            all_ok = False
    return all_ok


def stop_services():
    killed = 0
    for _, port in SERVICES:
        if not port_listening(port):
            continue
        r = run(["netstat", "-ano"])
        pids = set()
        for line in r.stdout.splitlines():
            if f":{port} " in line and "LISTENING" in line:
                parts = line.split()
                if parts:
                    pids.add(parts[-1])
        for pid in pids:
            if pid.isdigit() and run(["taskkill", "/PID", pid, "/F"]).returncode == 0:
                killed += 1
    ok(f"已停止 {killed} 个监听进程（gateway..auth 八服务；docker/模拟器/Metro 未动）")


# ---------- 模拟器 / Metro / App ----------

def adb_devices() -> list[str]:
    r = run([ADB, "devices"])
    return [l.split("\t")[0] for l in (r.stdout or "").splitlines()[1:] if "\tdevice" in l]


def ensure_emulator() -> bool:
    if adb_devices():
        ok(f"模拟器已在线：{', '.join(adb_devices())}")
        return True
    if not EMULATOR.exists():
        fail(f"未找到 emulator：{EMULATOR}")
        return False
    print("  ... 启动模拟器 Pixel_7")
    subprocess.Popen([str(EMULATOR), "-avd", "Pixel_7", "-no-snapshot-save", "-gpu", "auto"],
                     creationflags=CREATE_NO_WINDOW)
    t0 = time.time()
    while time.time() - t0 < 150:
        r = run([ADB, "shell", "getprop", "sys.boot_completed"])
        if r.stdout.strip() == "1":
            ok(f"模拟器已启动（{int(time.time() - t0)}s）")
            return True
        time.sleep(5)
    fail("模拟器启动超时")
    return False


def ensure_metro() -> bool:
    all_ok = True
    for port, proj in METRO_PORTS.items():
        if port_listening(port):
            ok(f"Metro :{port}（{proj.name}）已在跑")
            continue
        npx = shutil.which("npx")
        if not npx:
            fail("PATH 里没有 npx")
            all_ok = False
            continue
        log = LOG_DIR / f"metro-{port}.log"
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with open(log, "a", encoding="utf-8") as f:
            subprocess.Popen(["cmd", "/c", npx, "react-native", "start", "--port", str(port)],
                             cwd=str(proj), stdout=f, stderr=subprocess.STDOUT,
                             creationflags=CREATE_NO_WINDOW)
        good = False
        t0 = time.time()
        while time.time() - t0 < 90:
            time.sleep(3)
            if port_listening(port):
                good = True
                break
        (ok if good else fail)(f"Metro :{port}（{proj.name}）{'已拉起' if good else '启动失败，看 ' + str(log)}")
        all_ok &= good
    return all_ok


def start_apps():
    if not ensure_emulator():
        return
    for pkg in APPS:
        run([ADB, "shell", "pm", "list", "packages"])
        installed = run([ADB, "shell", "pm", "path", pkg])
        if installed.returncode != 0 or not installed.stdout.strip():
            warn(f"{pkg} 未安装（先 cd mobile*/android && ./gradlew.bat app:installDebug）")
            continue
        run([ADB, "shell", "am", "force-stop", pkg])
        run([ADB, "shell", "am", "start", "-n", f"{pkg}/.MainActivity"])
        ok(f"{pkg} 已（重）启动")
    print("  提示：App dev 构建依赖 Metro（代表端 8081 / 医生端 8082），未起请加 --app 一步到位")


# ---------- 体检 ----------

def check_all() -> bool:
    print("\n== 本机演示环境体检 ==")
    all_ok = True

    print("[Docker / 数据库]")
    if run(["docker", "ps"]).returncode != 0:
        fail("Docker 未运行")
        all_ok = False
    else:
        ps = psql("SELECT 1")
        if ps == "1":
            ok("postgres 可查询")
        else:
            fail("postgres 容器不可用（docker-compose up -d postgres redis）")
            all_ok = False

    print("[8 服务 /health]")
    for name, port in SERVICES:
        # 单次 2s 超时下 gateway 偶发瞬时抖动误报，FAIL 前隔 1s 复测一次
        good = http_ok(port) or (time.sleep(1) or http_ok(port))
        if good:
            ok(f"{name}(:{port})")
        else:
            fail(f"{name}(:{port}) 不通")
            all_ok = False

    print("[演示数据]")
    n = psql("SELECT count(*) FROM users WHERE phone IN ('13900001001','13900001002')")
    if n == "2":
        ok("demo_rep / demo_doctor 账号在库")
    else:
        warn(f"演示账号数={n or '查询失败'}（跑 --seed 补齐）")
    unread = psql("SELECT count(*) FROM notifications x JOIN users u ON u.id=x.user_id "
                  "WHERE u.phone='13900001001' AND x.is_read=false")
    ok(f"demo_rep 未读通知 {unread or '?'} 条（0 条时演示红点可先点一条通知重置）")
    exp = psql("SELECT min(filing_expire_date) FROM representative_qualifications q "
               "JOIN users u ON u.id=q.representative_id WHERE u.phone='13900001001'")
    ok(f"demo_rep 备案到期日 {exp or '?'}（必须在未来，过期会被 24h 扫描自动冻结）")

    print("[模拟器 / Metro / App]")
    devs = adb_devices()
    if devs:
        ok(f"模拟器在线：{', '.join(devs)}")
    else:
        warn("模拟器未开（--app 可拉起）")
    for port, proj in METRO_PORTS.items():
        (ok if port_listening(port) else warn)(f"Metro :{port}（{proj.name}）" +
                                               ("" if port_listening(port) else "未跑"))

    print("[网络 / config.ts]")
    ip = local_ip()
    for proj in ("mobile", "mobile-doctor"):
        cfg = ROOT / proj / "src" / "config.ts"
        m = re.search(r"^\s*const DEV_HOST = '([^']+)'", cfg.read_text(encoding="utf-8"), re.M)
        host = m.group(1) if m else "?"
        if host == "10.0.2.2":
            note = "模拟器模式"
        elif ip and host == ip:
            note = "真机模式（与本机 IP 一致）"
        else:
            note = f"与本机当前 IP {ip or '?'} 不一致——真机演示需改；模拟器建议 10.0.2.2"
        (ok if "不一致" not in note else warn)(f"{proj} DEV_HOST={host} → {note}")

    print("[.env 演示相关]")
    env = (ROOT / ".env").read_text(encoding="utf-8", errors="replace") if (ROOT / ".env").exists() else ""
    for key, want, desc in (("AUTH_DEV_MODE", "true", "验证码回传（联调取码用；上线必须关）"),):
        cur = re.search(rf"^{key}=(.+)$", env, re.M)
        val = cur.group(1).strip() if cur else "(未设)"
        (ok if val == want else warn)(f"{key}={val}（演示预期 {want}，{desc}）")

    print("== 体检结束 ==")
    return all_ok


def main():
    ap = argparse.ArgumentParser(description="MedAgent 本机演示环境一键拉起/体检")
    ap.add_argument("--check", action="store_true", help="只体检，不启动任何东西")
    ap.add_argument("--seed", action="store_true", help="默认流程后追加 seed_demo_data.py（幂等）")
    ap.add_argument("--app", action="store_true", help="追加：模拟器 + Metro 8081/8082 + 双端 App")
    ap.add_argument("--down", action="store_true", help="停 8 个 uvicorn（不动 docker/模拟器/Metro）")
    a = ap.parse_args()

    if a.down:
        print("\n== 停止后端服务 ==")
        stop_services()
        return

    if a.check:
        sys.exit(0 if check_all() else 1)

    print("\n== 拉起本机环境（幂等，缺什么补什么）==")
    if not ensure_docker():
        sys.exit(1)
    if not ensure_db():
        sys.exit(1)
    svc_ok = ensure_services()

    if a.seed:
        print("\n== 种子数据（幂等）==")
        r = run([sys.executable, str(ROOT / "scripts" / "seed_demo_data.py")], cwd=str(ROOT))
        tail = (r.stdout or r.stderr).strip().splitlines()[-3:]
        print("\n".join("  " + l for l in tail))

    if a.app:
        print("\n== 模拟器 / Metro / App ==")
        ensure_metro()
        start_apps()

    print("\n== 收尾体检 ==")
    check_all()
    sys.exit(0 if svc_ok else 1)


if __name__ == "__main__":
    main()
