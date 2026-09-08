#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自动获取闲鱼网页版 Cookie。
- 作为脚本运行：python get_cookie.py   （抓取后写入 .env）
- 作为模块导入：from get_cookie import fetch_cookie_via_edge
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from typing import Callable, Optional

from websockets.sync.client import connect

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(BASE_DIR, ".env")
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
DEBUG_PORT = 9222
PROFILE_DIR = os.path.join(BASE_DIR, ".edge_profile_tmp")
GOOFISH = "https://www.goofish.com"


def _http_json(url: str):
    with urllib.request.urlopen(url, timeout=3) as r:
        return json.loads(r.read())


def _wait_port() -> bool:
    for _ in range(40):
        try:
            _http_json(f"http://127.0.0.1:{DEBUG_PORT}/json/version")
            return True
        except Exception:
            time.sleep(0.5)
    return False


def _launch_edge() -> bool:
    if not os.path.exists(EDGE):
        return False
    cmd = [
        EDGE,
        f"--remote-debugging-port={DEBUG_PORT}",
        f"--user-data-dir={PROFILE_DIR}",
        "--no-first-run",
        "--no-default-browser-check",
        "--remote-allow-origins=*",
        GOOFISH,
    ]
    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return _wait_port()


def _page_ws():
    try:
        targets = _http_json(f"http://127.0.0.1:{DEBUG_PORT}/json")
    except Exception:
        return None
    for t in targets:
        if t.get("type") == "page" and "goofish" in t.get("url", ""):
            return t["webSocketDebuggerUrl"]
    for t in targets:
        if t.get("type") == "page":
            return t["webSocketDebuggerUrl"]
    return None


def _cdp_get_cookies(ws_url: str):
    with connect(ws_url) as ws:
        ws.send(json.dumps({"id": 1, "method": "Network.getAllCookies"}))
        while True:
            msg = json.loads(ws.recv(timeout=10))
            if msg.get("id") == 1:
                return msg.get("result", {}).get("cookies", [])


def _build_cookie_str(cookies) -> str:
    """只保留 goofish/taobao 域下的 cookie，拼成 k=v; k=v 串。"""
    keep = []
    for c in cookies:
        dom = c.get("domain", "")
        if "goofish" in dom or "taobao" in dom:
            keep.append(f"{c.get('name')}={c.get('value')}")
    seen, out = set(), []
    for kv in keep:
        if kv not in seen:
            seen.add(kv)
            out.append(kv)
    return "; ".join(out)


def fetch_cookie_via_edge(progress: Optional[Callable[[str], None]] = None) -> Optional[str]:
    """弹出 Edge 让用户登录，自动抓取闲鱼 Cookie。返回 cookie 字符串，失败返回 None。

    progress 回调用于上报阶段信息（如"等待登录"、"登录成功"），可选。
    """
    def report(s: str):
        if progress:
            progress(s)
        else:
            print(s)

    if not os.path.exists(EDGE):
        report("未找到 Edge 浏览器")
        return None

    if not _wait_port() and not _launch_edge():
        report("无法启动浏览器调试端口")
        return None

    report("浏览器已启动，请在弹出的窗口中登录闲鱼（扫码或账密）…")
    while True:
        ws = _page_ws()
        if not ws:
            time.sleep(2)
            continue
        try:
            cookies = _cdp_get_cookies(ws)
        except Exception:
            time.sleep(2)
            continue
        m = {c.get("name"): c.get("value") for c in cookies}
        if m.get("unb"):
            if not m.get("_m_h5_tk"):
                report("已检测到登录，但缺少 _m_h5_tk，继续等待…")
                time.sleep(2)
                continue
            report("登录成功，已抓取 Cookie")
            return _build_cookie_str(cookies)
        time.sleep(3)


def write_env(cookie_str: str):
    with open(ENV_PATH, "r", encoding="utf-8") as f:
        text = f.read()
    line = f"COOKIES_STR={cookie_str}"
    if re.search(r"^COOKIES_STR=", text, flags=re.M):
        text = re.sub(r"^COOKIES_STR=.*$", line, text, flags=re.M)
    else:
        text = text.rstrip("\n") + "\n" + line + "\n"
    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.write(text)


def main() -> int:
    cs = fetch_cookie_via_edge()
    if not cs:
        print("❌ 未获取到 Cookie")
        return 1
    write_env(cs)
    cookies = dict(kv.split("=", 1) for kv in cs.split("; ") if "=" in kv)
    tk = cookies.get("_m_h5_tk", "")
    print("✅ 登录成功，Cookie 已写入 .env")
    print(f"   unb      = {cookies.get('unb', '')}")
    print(f"   _m_h5_tk = {tk[:12]}…")
    print("   下一步：python main.py 启动服务即可。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
