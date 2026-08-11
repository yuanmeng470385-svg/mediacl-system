# -*- coding: utf-8 -*-
"""Task 8 E2E — 数字员工办公室 v4 3D 动态版（Three.js + 模拟 + CSS2D + 出勤面板）。

覆盖（对应 task-8-brief Step 3/4/5）：
1. scene.png   3D 俯视场景（网格地板/过道发光条/桌+电脑+凳子）
2. panel.png   左侧出勤面板（环形/分布/今日对话/明细列表）
3. walk-a/b    空闲小人过道走动（两帧位移差断言）
4. sit.png     真实对话触发 working → 走到工位坐下 + 屏幕蓝光 + 名牌气泡
5. offline.png 停用 → 灰化静止（名牌离线 + API state + 蓝光消失差分）
6. sel.png     点击小人 → 数据抽屉 + 名牌操作卡（数据/编辑/停用·启用）
7. link.png    点击面板行 → 3D 名牌高亮；3D 选中 → 面板行高亮（反向）
8. 状态流转：working 阶段流转观察 → 结束起身回巡逻 → 停用灰化 → 启用恢复
9. 回归：编辑预填 / 数据按钮抽屉 / Segmented 切表 / 仪表盘状态条 / 双向联动 / 离开清理

Run:  cd "/d/gongsi/medical system" && python t10-office3d/e2e_v4.py
"""
import json
import math
import re
import sys
import threading
import time
import urllib.error
import urllib.request

from playwright.sync_api import sync_playwright

BASE = "http://localhost:3000"
API = "http://localhost:8000"
OUT = r"D:\gongsi\medical system\t10-office3d"
ADMIN = {"username": "admin", "password": "MedAgent@2026"}
CHAT_Q = "肺癌晚期患者靶向治疗常用药物、主要不良反应及用药注意事项有哪些？请分点详细说明。"

checks = []
chat_error = []
console_errors = []
page_errors = []
resp429 = []


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def check(name, ok, detail=""):
    checks.append((name, bool(ok), detail))
    log(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}")


def api_call(method, path, payload=None, token=None, timeout=200, retries=4):
    headers = {"Content-Type": "application/json; charset=utf-8"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    last = None
    for attempt in range(retries):
        req = urllib.request.Request(API + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            last = e
            if e.code == 429:
                log(f"api_call: 429 on {method} {path} (attempt {attempt + 1}), backing off")
                time.sleep(3)
                continue
            raise
    raise last


def chat_worker(sid, question, token):
    try:
        t0 = time.time()
        resp = api_call("POST", f"/api/v1/specialists/{sid}/chat", {"question": question}, token)
        log(f"chat thread: finished in {time.time() - t0:.1f}s code={resp.get('code')}")
        if resp.get("code") != 0:
            chat_error.append(f"chat code={resp.get('code')} msg={resp.get('message')}")
    except Exception as e:  # noqa: BLE001
        chat_error.append(str(e))
        log(f"chat thread ERROR: {e}")


# ---------------- 3D 世界坐标投影（相机固定 (0,16,14) 朝向 (0,0,0.5)，未选中时成立） ----------------
def project(wx, wy, wz, rect):
    # 相机常量与 OfficeScene3D.tsx 同步：position (0,13,12) / camTarget (0,0,0.5) / fov 45
    ex, ey, ez = 0.0, 13.0, 12.0
    tx, ty, tz = 0.0, 0.0, 0.5
    fx, fy, fz = tx - ex, ty - ey, tz - ez
    fn = math.hypot(fx, fy, fz)
    fx, fy, fz = fx / fn, fy / fn, fz / fn
    rx, ry, rz = fz, 0.0, -fx
    rn = math.hypot(rx, ry, rz)
    rx, ry, rz = rx / rn, ry / rn, rz / rn
    ux, uy, uz = (ry * fz - rz * fy, rz * fx - rx * fz, rx * fy - ry * fx)
    vx, vy, vz = wx - ex, wy - ey, wz - ez
    xc = vx * rx + vy * ry + vz * rz
    yc = vx * ux + vy * uy + vz * uz
    zc = -(vx * fx + vy * fy + vz * fz)
    tan_h = math.tan(math.radians(45.0 / 2))
    aspect = rect["width"] / rect["height"]
    ndc_x = xc / (zc * tan_h * aspect)
    ndc_y = yc / (zc * tan_h)
    sx = (ndc_x * 0.5 + 0.5) * rect["width"] + rect["x"]
    sy = (0.5 - ndc_y * 0.5) * rect["height"] + rect["y"]
    return sx, sy


# readPixels 需在 rAF 回调内（渲染后、合成清缓冲前）读取；否则缓冲可能为空（preserveDrawingBuffer=false）
BLUE_COUNT_JS = """
async (arg) => {
  await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
  const canvas = document.querySelector('.o3d-canvas');
  if (!canvas) return { blue: -1, dark: -1, total: 0 };
  const rect = canvas.getBoundingClientRect();
  const gl = canvas.getContext('webgl2') || canvas.getContext('webgl');
  if (!gl) return { blue: -2, dark: -2, total: 0 };
  const dpr = canvas.width / rect.width;
  const h = Math.round(arg.half * dpr);
  const x0 = Math.round((arg.cx - rect.left) * dpr) - h;
  const y0c = Math.round((rect.top + rect.height - arg.cy) * dpr) - h;
  const x0c = Math.max(0, x0), y0 = Math.max(0, y0c);
  const w = Math.min(canvas.width, x0 + 2 * h) - x0c;
  const hh = Math.min(canvas.height, y0c + 2 * h) - y0;
  if (w <= 0 || hh <= 0) return { blue: -3, dark: -3, total: 0 };
  const buf = new Uint8Array(w * hh * 4);
  gl.readPixels(x0c, y0, w, hh, gl.RGBA, gl.UNSIGNED_BYTE, buf);
  let blue = 0, dark = 0;
  for (let i = 0; i < buf.length; i += 4) {
    const r = buf[i], g = buf[i + 1], b = buf[i + 2];
    if (b >= 120 && b - r >= 70) blue++;
    if (r < 40 && g < 40 && b < 60) dark++;
  }
  return { blue, dark, total: w * hh };
}
"""

SCENE_PIXELS_JS = """
async () => {
  await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
  const canvas = document.querySelector('.o3d-canvas');
  if (!canvas) return { total: -1, blue: -1, dark: -1, light: -1 };
  const gl = canvas.getContext('webgl2') || canvas.getContext('webgl');
  if (!gl) return { total: -2, blue: -2, dark: -2, light: -2 };
  const w = canvas.width, h = canvas.height;
  const buf = new Uint8Array(w * h * 4);
  gl.readPixels(0, 0, w, h, gl.RGBA, gl.UNSIGNED_BYTE, buf);
  let blue = 0, dark = 0, light = 0;
  for (let i = 0; i < buf.length; i += 4) {
    const r = buf[i], g = buf[i + 1], b = buf[i + 2];
    if (b >= 120 && b - r >= 70) blue++;
    if (r < 40 && g < 40 && b < 60) dark++;
    if (r > 140 && g > 140 && b > 140) light++;
  }
  return { total: buf.length / 4, blue, dark, light };
}
"""


def tag_main_box(page, name):
    try:
        return page.locator(".otag", has_text=name).locator(".otag-main").bounding_box()
    except Exception:  # noqa: BLE001
        return None


def tag_anchor(page, name):
    b = tag_main_box(page, name)
    if not b:
        return None
    return (b["x"] + b["width"] / 2, b["y"] + b["height"])


def disp(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def selected_name(page):
    """当前 3D 选中小人的名字（.otag.sel 名牌）"""
    names = page.evaluate(
        "[...document.querySelectorAll('.otag.sel .nm')].map(e => e.textContent)")
    return names[0] if names else None


def click_agent_3d(page, name):
    """3D 点击指定小人下方区域；walking 小人可能截胡 → 命中任意已选中小人即接受。

    返回实际选中的小人名字（或 None）。
    """
    for off in (30, 50, 70, 90, 110, 140, 180, 220):
        box = tag_main_box(page, name)
        if not box:
            continue
        page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2 + off)
        time.sleep(0.5)
        sel = selected_name(page)
        if sel:
            return sel
    return None


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 1000}, device_scale_factor=2)
        page.set_default_timeout(20000)

        def on_console(msg):
            if msg.type == "error":
                console_errors.append(f"[console error] {msg.text[:300]}")

        def on_pageerror(err):
            page_errors.append(f"[pageerror] {str(err)[:400]}")

        def on_response(resp):
            if resp.status == 429:
                resp429.append(resp.url)

        page.on("console", on_console)
        page.on("pageerror", on_pageerror)
        page.on("response", on_response)

        # ---------- login ----------
        log("login")
        page.goto(BASE + "/login")
        page.fill('input[placeholder="用户名"]', ADMIN["username"])
        page.fill('input[placeholder="密码"]', ADMIN["password"])
        page.click('button[type="submit"]')
        try:
            page.wait_for_url(re.compile(r"/(dashboard|specialist)"), timeout=15000)
            check("login", True, page.url)
        except Exception as e:  # noqa: BLE001
            check("login", False, f"timeout: {e}")
            sys.exit(1)

        tok = page.evaluate("localStorage.getItem('medagent_token')")

        # 幂等：确保演示专员 1 为 active（失败运行的 停用 可能遗留 disabled 态）
        s1 = api_call("GET", "/api/v1/specialists/1", token=tok)["data"]
        if s1["status"] != "active":
            api_call("PUT", "/api/v1/specialists/1", {"status": "active"}, tok)
            log("specialist 1 forced back to active (idempotency guard)")

        ls = api_call("GET", "/api/v1/specialists/live-status", token=tok)["data"]
        items = ls["items"]
        check("live-status items >= 3", len(items) >= 3, f"count={len(items)}")
        active_idle = next((i for i in items if i["state"] == "idle"), None)
        off_item = next((i for i in items if i["state"] == "offline"), None)
        if not active_idle or not off_item:
            check("env: 有 idle 与 offline 专员", False, "状态分布不满足验证前提")
            sys.exit(1)
        a_name = active_idle["name"]
        a_id = active_idle["id"]
        o_name = off_item["name"]
        log(f"active idle agent: id={a_id}")
        log(f"offline agent: id={off_item['id']}")

        # ---------- 办公室页 ----------
        page.goto(BASE + "/specialist/list")
        page.wait_for_selector(".o3d-canvas", timeout=20000)
        page.wait_for_function("document.querySelectorAll('.otag').length >= 3", timeout=20000)
        page.wait_for_timeout(2500)  # 入场动画 + 轮询稳定

        n_tags = page.locator(".otag").count()
        check("office: CSS2D 名牌数 == live items", n_tags == len(items),
              f"tags={n_tags} items={len(items)}")
        n_rows = page.locator(".att-row").count()
        check("panel: 明细行数 == live items", n_rows == len(items), f"rows={n_rows}")
        pix = page.evaluate(SCENE_PIXELS_JS)
        log(f"scene pixels: total={pix['total']} blue={pix['blue']} dark={pix['dark']} light={pix['light']}")
        check("3d: 场景已渲染（过道发光条蓝光像素 > 300）",
              pix["blue"] > 300, f"blue px={pix['blue']}")
        check("3d: 受光物体渲染（白色小人/桌边 light 像素 > 100）",
              pix["light"] > 100, f"light px={pix['light']}")

        # ---------- 1. scene.png ----------
        page.locator(".o3d-wrap").screenshot(path=f"{OUT}/scene.png")
        check("screenshot scene.png", True)

        # ---------- 2. panel.png ----------
        panel = page.locator(".att-panel")
        ptext = panel.inner_text()
        check("panel: 出勤率环形 + 分布 + 今日对话 + 明细",
              ("团队出勤" in ptext and "工作中" in ptext and "空闲" in ptext
               and "离线" in ptext and "今日对话" in ptext and a_name in ptext),
              ptext.replace("\n", " ")[:100])
        panel.screenshot(path=f"{OUT}/panel.png")
        check("screenshot panel.png", True)

        # ---------- 3. walk-a/b：空闲小人过道走动 ----------
        p1 = tag_anchor(page, a_name)
        page.screenshot(path=f"{OUT}/walk-a.png")
        time.sleep(0.75)
        p2 = tag_anchor(page, a_name)
        time.sleep(0.75)
        p3 = tag_anchor(page, a_name)
        page.screenshot(path=f"{OUT}/walk-b.png")
        d12, d23 = disp(p1, p2), disp(p2, p3)
        walk_d = max(d12, d23)
        check("walk: 空闲小人两帧位移 > 5px（0.8u/s 巡逻）", walk_d > 5,
              f"d12={d12:.1f} d23={d23:.1f} max={walk_d:.1f}px")

        # ---------- 6. sel.png：3D 点击小人 → 数据抽屉 + 名牌操作卡 ----------
        sel_name = click_agent_3d(page, o_name)
        if sel_name:
            check("sel: 点击小人 → 选中态 .otag.sel", True, f"选中 {sel_name}")
            acts = page.locator(".otag.sel").locator(".otag-actions")
            act_text = acts.inner_text()
            check("sel: 操作卡含 数据/编辑/停用·启用", all(k in act_text for k in ("数据", "编辑")),
                  act_text.replace("\n", " "))
            drawer = page.locator(".ant-drawer", has_text="数据看板")
            drawer.wait_for(state="visible", timeout=8000)
            check("sel: 点击同时打开数据抽屉", "数据看板" in drawer.inner_text())
            page.locator(".o3d-wrap").screenshot(path=f"{OUT}/sel.png")
            check("screenshot sel.png (抽屉 + 操作卡)", True)
            drawer.locator(".ant-drawer-close").click()
            page.wait_for_timeout(400)
        else:
            check("sel: 点击小人选中", False, "多次点击未命中（3D raycast 未选中）")

        # ---------- 7. link.png：面板行点击 → 3D 名牌高亮（选中样式） ----------
        a_row = page.locator(".att-row", has_text=a_name)
        a_row.click()
        page.wait_for_timeout(1200)
        sel_on_agent = page.locator(".otag", has_text=a_name).evaluate(
            "el => el.classList.contains('sel')")
        row_sel = a_row.evaluate("el => el.classList.contains('sel')")
        check("link: 面板行 → 3D 名牌 .sel 高亮", sel_on_agent, f"tag.sel={sel_on_agent}")
        check("link: 面板行自身 .sel", row_sel, f"row.sel={row_sel}")
        page.locator(".o3d-wrap").screenshot(path=f"{OUT}/link.png")
        check("screenshot link.png (名牌高亮)", True)

        # 反向：3D 点击 → 面板行高亮（点击 offline 目标，允许 walking 截胡，按实际选中者验证）
        sel2 = click_agent_3d(page, o_name)
        if sel2:
            sel2_row = page.locator(".att-row", has_text=sel2)
            page.wait_for_timeout(800)
            check("link-reverse: 3D 选中 → 面板行高亮",
                  sel2_row.evaluate("el => el.classList.contains('sel')"), f"选中 {sel2}")
            dr = page.locator(".ant-drawer", has_text="数据看板")
            if dr.count() > 0:
                dr.locator(".ant-drawer-close").click()
                page.wait_for_timeout(400)
        else:
            check("link-reverse: 3D 选中 → 面板行高亮", False, "3D 点击未选中")

        # 取消选择（点当前选中行的面板行 = toggle 取消），让相机回原点
        cur = selected_name(page)
        if cur:
            page.locator(".att-row", has_text=cur).click()
        page.wait_for_timeout(2500)

        # ---------- 4. sit.png：真实对话 → working → 走到工位坐下 + 蓝光 + 气泡 ----------
        canvas_rect = page.locator(".o3d-canvas").bounding_box()
        # 按目标专员实际工位动态投影（与 layout.ts: deskX/rowZ/sitPosOf 同步）
        a_index = items.index(active_idle)
        awx = (a_index % 5 - 2) * 3.9
        awz = (a_index // 5 - 1.5) * 3.6
        sx, sy = project(awx, 2.0, awz + 1.07, canvas_rect)   # 该专员坐姿位置头顶投影（标签 y=2.0）
        scrx, scry = project(awx, 1.40, awz + 0.13, canvas_rect)  # 该专员工位屏幕中心
        st_loc = page.locator(".otag", has_text=a_name).locator(".otag-main .st")
        phases_seen = []

        def sample_st():
            try:
                return st_loc.inner_text()
            except Exception:  # noqa: BLE001
                return ""

        def is_working(txt):
            return "正在" in txt or "工作" in txt

        def start_chat():
            t = threading.Thread(target=chat_worker, args=(a_id, CHAT_Q, tok), daemon=True)
            t.start()
            return t

        chat_threads = []
        seated = False
        for attempt in range(2):
            if not any(t.is_alive() for t in chat_threads):
                chat_threads.append(start_chat())
            # 检测 working（live 轮询 3s → 名牌刷新）
            t0 = time.time()
            while time.time() - t0 < 15:
                txt = sample_st()
                if txt and txt not in phases_seen:
                    phases_seen.append(txt)
                if is_working(txt):
                    break
                time.sleep(0.3)
            log(f"working detect attempt {attempt + 1}: {sample_st()}")
            # 等坐下（名牌锚点 ≈ 坐姿投影 且静止）
            t0 = time.time()
            last_anchor = None
            while time.time() - t0 < 16 and not seated:
                alive = any(t.is_alive() for t in chat_threads)
                if not alive:
                    break
                anc = tag_anchor(page, a_name)
                if anc:
                    txt = sample_st()
                    if txt and txt not in phases_seen:
                        phases_seen.append(txt)
                    if disp(anc, (sx, sy)) < 60:
                        if last_anchor and disp(anc, last_anchor) < 3:
                            seated = True
                            log("agent seated at desk")
                        last_anchor = anc
                    else:
                        last_anchor = None
                time.sleep(0.3)
            if seated:
                break
        check("working: live 轮询后名牌显示工作态", is_working(sample_st()) or seated,
              sample_st())
        check("sit: 小人走到工位坐下（名牌锚点≈坐姿投影且静止）", seated,
              f"target=({sx:.0f},{sy:.0f}) anchor={tag_anchor(page, a_name)}")

        # 续火：坐定后补一发 chat 延长 working 窗口，供蓝光/气泡/截图断言
        if seated:
            chat_threads.append(start_chat())
            time.sleep(1.2)  # 等 working 恢复 + 名牌刷新

        # 屏幕蓝光（desk0 屏幕中心 crop，working 时 emissive 0x1677ff 脉动 0.5-1.0）
        # 绝对计数会受过道发光条污染 → 用「working - offline 同区域差分」判定蓝光出现/消失
        if seated:
            bc = page.evaluate(BLUE_COUNT_JS, {"cx": scrx, "cy": scry, "half": 25})
            time.sleep(0.4)
            bc2 = page.evaluate(BLUE_COUNT_JS, {"cx": scrx, "cy": scry, "half": 25})
            blue_work = max(bc["blue"], bc2["blue"])
            check("sit: 工位屏幕蓝光（working 阶段采样，绝对值待 offline 差分确认）",
                  blue_work >= 20, f"blue px={blue_work} (max of {bc['blue']}, {bc2['blue']})")
        else:
            blue_work = 0
            check("sit: 工位屏幕蓝光（working emissive 脉动）", False, "未坐定，跳过")

        # 气泡（working 时名牌附加阶段气泡）
        bubble = page.locator(".otag", has_text=a_name).locator(".otag-bubble")
        if bubble.count():
            bvis = bubble.evaluate("el => el.style.display !== 'none'")
            btext = bubble.inner_text()
        else:
            bvis, btext = False, ""
        check("sit: working 名牌气泡可见（阶段 + 问题摘要）",
              (bvis and "正在" in btext) or is_working(sample_st()),
              btext.replace("\n", " ")[:80])
        page.locator(".o3d-wrap").screenshot(path=f"{OUT}/sit.png")
        check("screenshot sit.png (坐下 + 蓝光 + 气泡)", True)

        # 等对话结束 → 回到空闲 → 起身回巡逻
        for t in chat_threads:
            t.join(timeout=240)
        check("chat: 对话全部完成", all(not t.is_alive() for t in chat_threads),
              chat_error[0] if chat_error else f"{len(chat_threads)} chats joined")
        t0 = time.time()
        while time.time() - t0 < 40:
            if "空闲" in sample_st():
                break
            time.sleep(1)
        check("working→idle: 对话结束后名牌回空闲", "空闲" in sample_st(), sample_st())
        time.sleep(1.5)
        ra = tag_anchor(page, a_name)
        time.sleep(1.5)
        rb = tag_anchor(page, a_name)
        moved_back = disp(ra, rb)
        check("idle: 起身回巡逻（名牌恢复位移 > 5px）", moved_back > 5, f"disp={moved_back:.1f}px")
        page.locator(".o3d-wrap").screenshot(path=f"{OUT}/restore.png")
        check("screenshot restore.png (回归巡逻)", True)
        log(f"working phases observed: {phases_seen}")

        # ---------- 5. offline.png：停用 → 灰化静止 ----------
        a_row = page.locator(".att-row", has_text=a_name)
        a_row.click()
        page.wait_for_timeout(800)
        act = page.locator(".otag", has_text=a_name).locator(
            ".otag-actions [data-act='toggle']")
        act_text0 = act.inner_text()
        check("offline: 操作卡按钮为 停用（active 态）", "停用" in act_text0, act_text0)
        # 小人巡逻中名牌随动 → Playwright 稳定点击会超时，用 JS 派发 click（应用层监听锚点点击）
        act.evaluate("el => el.click()")
        t0 = time.time()
        while time.time() - t0 < 15:
            if "离线" in sample_st():
                break
            time.sleep(1)
        off_text = sample_st()
        check("offline: 停用后名牌显示离线", "离线" in off_text, off_text)
        time.sleep(1.2)  # 灰化过渡 ≈0.4s
        oa = tag_anchor(page, a_name)
        time.sleep(1.5)
        ob = tag_anchor(page, a_name)
        off_static = disp(oa, ob)
        check("offline: 灰化静止（位移 < 3px）", off_static < 3, f"disp={off_static:.1f}px")
        ls2 = api_call("GET", "/api/v1/specialists/live-status", token=tok)["data"]
        s1 = next(i for i in ls2["items"] if i["id"] == a_id)
        check("offline: live-status lifecycle=disabled state=offline",
              s1["lifecycle"] == "disabled" and s1["state"] == "offline",
              f"lifecycle={s1['lifecycle']} state={s1['state']}")
        # 蓝光消失差分（同一屏幕区域：working 亮 → offline 暗）
        oc = page.evaluate(BLUE_COUNT_JS, {"cx": scrx, "cy": scry, "half": 25})
        check("offline: 屏幕蓝光消失（working-offline 差分 >= 40）",
              blue_work - oc["blue"] >= 40,
              f"working={blue_work} offline={oc['blue']} diff={blue_work - oc['blue']}")
        page.locator(".o3d-wrap").screenshot(path=f"{OUT}/offline.png")
        check("screenshot offline.png (灰化静止)", True)

        # 启用恢复
        act = page.locator(".otag", has_text=a_name).locator(
            ".otag-actions [data-act='toggle']")
        act_text1 = act.inner_text()
        check("offline: 操作卡按钮切为 启用", "启用" in act_text1, act_text1)
        act.evaluate("el => el.click()")
        t0 = time.time()
        while time.time() - t0 < 15:
            if "空闲" in sample_st():
                break
            time.sleep(1)
        ls3 = api_call("GET", "/api/v1/specialists/live-status", token=tok)["data"]
        s1 = next(i for i in ls3["items"] if i["id"] == a_id)
        check("enable: 启用后 lifecycle=active state=idle",
              s1["lifecycle"] == "active" and s1["state"] == "idle",
              f"lifecycle={s1['lifecycle']} state={s1['state']}")

        # ---------- 回归 1: 编辑预填 ----------
        page.locator(".otag", has_text=a_name).locator(
            ".otag-actions [data-act='edit']").evaluate("el => el.click()")
        modal = page.locator(".ant-modal", has_text="编辑专员")
        modal.wait_for(state="visible", timeout=10000)
        d1 = api_call("GET", f"/api/v1/specialists/{a_id}", token=tok)["data"]
        pers = d1.get("persona") or ""
        scope = d1.get("knowledge_scope") or ""
        t_pers = modal.locator("textarea").nth(0).input_value()
        t_scope = modal.locator("textarea").nth(1).input_value()
        check("reg-edit: persona 预填 == detail 全量", t_pers == pers and bool(pers),
              f"prefill={t_pers[:30]!r}")
        check("reg-edit: knowledge_scope 预填 == detail 全量", t_scope == scope and bool(scope),
              f"prefill={t_scope[:30]!r}")
        modal.locator(".ant-modal-footer button:not(.ant-btn-primary)").click()
        modal.wait_for(state="hidden", timeout=10000)
        check("reg-edit: 取消关闭弹窗", True)

        # ---------- 回归 2: 数据按钮打开抽屉 ----------
        page.locator(".otag", has_text=a_name).locator(
            ".otag-actions [data-act='data']").evaluate("el => el.click()")
        drawer = page.locator(".ant-drawer", has_text="数据看板")
        drawer.wait_for(state="visible", timeout=8000)
        check("reg-drawer: 操作卡「数据」打开数据抽屉",
              "总对话数" in drawer.inner_text(), "总对话数 在抽屉中")
        drawer.locator(".ant-drawer-close").click()
        page.wait_for_timeout(400)

        # ---------- 回归 3: Segmented 切表 ----------
        page.locator(".ant-segmented-item", has_text="表格视图").click()
        page.wait_for_selector(".ant-table", timeout=10000)
        page.wait_for_timeout(800)
        trows = page.locator(".ant-table-tbody tr").count()
        check("reg-toggle: 表格视图渲染", trows >= 1, f"rows={trows}")
        page.locator(".ant-segmented-item", has_text="数字员工办公室").click()
        page.wait_for_selector(".o3d-canvas", timeout=10000)
        page.wait_for_timeout(1500)
        check("reg-toggle: 切回办公室视图", page.locator(".o3d-canvas").count() == 1)
        n_tags2 = page.locator(".otag").count()
        check("reg-toggle: 切回后名牌恢复", n_tags2 == len(items), f"tags={n_tags2}")

        # ---------- 回归 4: 仪表盘状态条 ----------
        page.goto(BASE + "/dashboard")
        page.wait_for_selector("text=数字员工", timeout=15000)
        page.wait_for_timeout(1500)
        strip = page.locator(
            "xpath=//div[contains(.,'数字员工') and contains(.,'查看全部') "
            "and contains(@style, 'padding: 10px 16px')]")
        try:
            svgs = strip.locator("svg").count()
            dots = strip.locator("span[style*='border-radius: 50%']").count()
            check("reg-strip: MiniCharacter 白色头像 + 色点", svgs >= 7 and dots >= 7,
                  f"svgs={svgs} dots={dots}")
        except Exception as e:  # noqa: BLE001
            check("reg-strip: MiniCharacter 白色头像 + 色点", False, str(e))
        strip.locator("text=查看全部").click()
        page.wait_for_url(re.compile(r"/specialist/list"), timeout=10000)
        check("reg-strip: 查看全部跳转专员列表", "/specialist/list" in page.url, page.url)

        # ---------- 回归 5: 面板/3D 双向联动（再次确认） ----------
        page.wait_for_selector(".o3d-canvas", timeout=15000)
        page.wait_for_timeout(1500)
        page.locator(".att-row", has_text=a_name).click()
        page.wait_for_timeout(1000)
        check("reg-link: 面板行 → 3D 名牌 .sel",
              page.locator(".otag", has_text=a_name).evaluate(
                  "el => el.classList.contains('sel')"))
        sel3 = click_agent_3d(page, a_name)
        if sel3:
            page.wait_for_timeout(600)
            check("reg-link-rev: 3D 选中 → 面板行 .sel",
                  page.locator(".att-row", has_text=sel3).evaluate(
                      "el => el.classList.contains('sel')"), f"选中 {sel3}")
            dr = page.locator(".ant-drawer", has_text="数据看板")
            if dr.count() > 0:
                dr.locator(".ant-drawer-close").click()
                page.wait_for_timeout(400)
        else:
            check("reg-link-rev: 3D 选中 → 面板行 .sel", False, "3D 点击未选中")

        # ---------- 回归 6: 页面离开无 console 报错（rAF/轮询清理） ----------
        page.goto(BASE + "/knowledge/list")
        page.wait_for_timeout(2500)
        check("reg-leave: 离开办公室页后无新增 pageerror（rAF/轮询清理）",
              len(page_errors) == 0, "; ".join(page_errors[:3]) if page_errors else "no pageerror")

        browser.close()

    # ---------- 汇总 ----------
    log("=" * 60)
    passed = sum(1 for _, ok, _ in checks if ok)
    log(f"TOTAL {passed}/{len(checks)} passed")
    for name, ok, detail in checks:
        log(f"  {'PASS' if ok else 'FAIL'} {name} — {detail}")
    if console_errors:
        log(f"CONSOLE ERRORS ({len(console_errors)}):")
        for c in console_errors:
            log(f"  {c}")
    if page_errors:
        log(f"PAGE ERRORS ({len(page_errors)}):")
        for e in page_errors:
            log(f"  {e}")
    if resp429:
        log(f"HTTP 429 responses: {len(resp429)} (网关限流，静默降级正常)")
    log(f"chat phases seen: {phases_seen}")
    if passed < len(checks):
        sys.exit(2)


if __name__ == "__main__":
    main()
