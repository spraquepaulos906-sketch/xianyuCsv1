"""Web 后端：提供前端页面与多模型配置 API。"""
import os
import socket
import threading
from typing import Optional

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from loguru import logger

import config_manager
from context_manager import ChatContextManager
from dotenv import set_key
from utils.xianyu_utils import trans_cookies

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

app = FastAPI(title="xianyuCsv1")

# 运行时注入的全局实例（由 main.py 设置）
_bot = None   # XianyuReplyBot
_live = None  # XianyuLive

# 自动连接闲鱼的后台任务状态（供前端轮询）
_auto_state = {"running": False, "done": False, "ok": False, "message": ""}
_auto_lock = threading.Lock()


def set_runtime(bot, live) -> None:
    """由 main.py 在启动时注入 bot 和 live 实例。"""
    global _bot, _live
    _bot = bot
    _live = live


# ---------- Web 监听管理（支持局域网开关热切换） ----------
_web_state = {
    "host": "127.0.0.1",
    "port": 8000,
    "server": None,
    "thread": None,
}
_web_lock = threading.Lock()


def _local_lan_ip() -> str:
    """获取本机局域网 IP（用于展示访问地址）。"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def start_web(host: str, port: int) -> None:
    """启动 Web 服务（后台线程）。由 main.py 调用。"""
    with _web_lock:
        _web_state["host"] = host
        _web_state["port"] = port
        config = uvicorn.Config(app, host=host, port=port, log_level="warning")
        server = uvicorn.Server(config)
        _web_state["server"] = server
        thread = threading.Thread(target=server.run, daemon=True)
        _web_state["thread"] = thread
        thread.start()


def restart_web(host: str, port: int) -> None:
    """停止旧监听并启动新监听（后台线程执行，避免阻塞请求）。"""
    def _run():
        with _web_lock:
            old_server = _web_state.get("server")
            old_thread = _web_state.get("thread")
            if old_server is not None:
                old_server.should_exit = True
        if old_thread is not None and old_thread is not threading.current_thread():
            old_thread.join(timeout=10)
        with _web_lock:
            config = uvicorn.Config(app, host=host, port=port, log_level="warning")
            server = uvicorn.Server(config)
            _web_state["host"] = host
            _web_state["port"] = port
            _web_state["server"] = server
            thread = threading.Thread(target=server.run, daemon=True)
            _web_state["thread"] = thread
            thread.start()

    threading.Thread(target=_run, daemon=True).start()


class ModelPayload(BaseModel):
    provider: str
    api_key: str
    base_url: str
    model_name: str


def _runtime_status() -> dict:
    connected = bool(_live and getattr(_live, "ws", None))
    return {
        "connected": connected,
        "current_model_id": getattr(_bot, "current_model_id", None),
        "current_model_name": getattr(_bot, "current_model_name", None),
    }


@app.get("/api/config")
def get_config():
    models = config_manager.list_models()
    current = config_manager.get_current_model()
    return {
        "models": models,
        "current_id": current.get("id") if current else None,
        "status": _runtime_status(),
    }


@app.post("/api/models")
def add_model(payload: ModelPayload):
    if not payload.provider or not payload.api_key or not payload.base_url or not payload.model_name:
        raise HTTPException(status_code=400, detail="provider / api_key / base_url / model_name 均不能为空")
    entry = config_manager.add_model(
        payload.provider, payload.api_key, payload.base_url, payload.model_name
    )
    return {"ok": True, "model": entry}


@app.put("/api/models/{model_id}")
def update_model(model_id: str, payload: ModelPayload):
    if not payload.provider or not payload.base_url or not payload.model_name:
        raise HTTPException(status_code=400, detail="provider / base_url / model_name 均不能为空")
    entry = config_manager.update_model(
        model_id, payload.provider, payload.api_key, payload.base_url, payload.model_name
    )
    if entry is None:
        raise HTTPException(status_code=404, detail="模型不存在")
    # 如果更新的是当前模型，热刷新 client
    if entry.get("is_current") and _bot:
        _bot.switch_model(model_id)
    return {"ok": True, "model": entry}


@app.delete("/api/models/{model_id}")
def delete_model(model_id: str):
    if not config_manager.delete_model(model_id):
        raise HTTPException(status_code=404, detail="模型不存在")
    # 删除后若切换了当前模型，刷新 bot
    if _bot:
        current = config_manager.get_current_model()
        if current and _bot.current_model_id != current.get("id"):
            _bot.switch_model(current.get("id"))
    return {"ok": True}


@app.post("/api/models/{model_id}/activate")
def activate_model(model_id: str):
    if config_manager.get_model_by_id(model_id) is None:
        raise HTTPException(status_code=404, detail="模型不存在")
    if _bot:
        if not _bot.switch_model(model_id):
            raise HTTPException(status_code=500, detail="切换模型失败")
    else:
        config_manager.set_current(model_id)
    return {"ok": True}


# ---------- 对话日志 ----------
_readonly_ctx = None


def _ctx() -> ChatContextManager:
    """返回聊天上下文管理器：优先复用值守实例，否则用只读实例（未连接时也能查历史）。"""
    global _readonly_ctx
    if _live is not None and getattr(_live, "context_manager", None) is not None:
        return _live.context_manager
    if _readonly_ctx is None:
        _readonly_ctx = ChatContextManager()
    return _readonly_ctx


@app.get("/api/conversations")
def list_conversations(limit: int = 200):
    try:
        conversations = _ctx().list_conversations(limit=limit)
    except Exception as e:
        logger.error(f"读取会话列表失败: {e}")
        raise HTTPException(status_code=500, detail=f"读取会话列表失败: {e}")
    return {"conversations": conversations}


@app.get("/api/conversations/{chat_id}")
def get_conversation(chat_id: str):
    try:
        messages = _ctx().get_messages_by_chat(chat_id)
    except Exception as e:
        logger.error(f"读取会话 {chat_id} 失败: {e}")
        raise HTTPException(status_code=500, detail=f"读取会话失败: {e}")
    return {"chat_id": chat_id, "messages": messages}


# ---------- 网络访问（局域网开关） ----------
class NetworkPayload(BaseModel):
    lan_enabled: bool


def _is_lan_host(host: str) -> bool:
    return host in ("0.0.0.0", "::")


def _apply_web_host(host: str) -> None:
    """持久化 WEB_HOST 到 .env 并更新当前进程环境。"""
    env_path = os.path.join(config_manager.BASE_DIR, ".env")
    try:
        set_key(env_path, "WEB_HOST", host)
    except Exception as e:
        logger.warning(f"写入 WEB_HOST 到 .env 失败: {e}")
    os.environ["WEB_HOST"] = host


@app.get("/api/network")
def get_network():
    host = _web_state.get("host", "127.0.0.1")
    port = _web_state.get("port", 8000)
    lan_enabled = _is_lan_host(host)
    lan_url = f"http://{_local_lan_ip()}:{port}" if lan_enabled else ""
    return {
        "host": host,
        "port": port,
        "lan_enabled": lan_enabled,
        "lan_url": lan_url,
    }


@app.post("/api/network")
def set_network(payload: NetworkPayload):
    port = _web_state.get("port", 8000)
    new_host = "0.0.0.0" if payload.lan_enabled else "127.0.0.1"
    if new_host == _web_state.get("host", "127.0.0.1"):
        return {"ok": True, "changed": False, "host": new_host, "port": port,
                "lan_enabled": payload.lan_enabled,
                "lan_url": f"http://{_local_lan_ip()}:{port}" if payload.lan_enabled else ""}
    _apply_web_host(new_host)
    restart_web(new_host, port)
    return {"ok": True, "changed": True, "host": new_host, "port": port,
            "lan_enabled": payload.lan_enabled,
            "lan_url": f"http://{_local_lan_ip()}:{port}" if payload.lan_enabled else ""}


class CookiePayload(BaseModel):
    cookies_str: str


def _mask_cookie(cookies_str: str) -> str:
    """cookie 脱敏显示：仅保留首尾各 8 个字符。"""
    if not cookies_str:
        return ""
    if len(cookies_str) <= 20:
        return "****"
    return f"{cookies_str[:8]}……{cookies_str[-8:]}"


@app.get("/api/cookie")
def get_cookie():
    cookies_str = os.getenv("COOKIES_STR", "")
    is_set = bool(cookies_str) and cookies_str != "your_cookies_here"
    return {"is_set": is_set, "cookie_masked": _mask_cookie(cookies_str) if is_set else ""}


def _apply_cookie(cookies_str: str) -> None:
    """持久化 cookie 到 .env 并热重连值守。"""
    env_path = os.path.join(config_manager.BASE_DIR, ".env")
    try:
        set_key(env_path, "COOKIES_STR", cookies_str)
    except Exception as e:
        logger.warning(f"写入 .env 失败: {e}")
    os.environ["COOKIES_STR"] = cookies_str
    if _live is not None:
        _live.update_cookie(cookies_str)
        _live.request_restart()


@app.post("/api/cookie")
def set_cookie(payload: CookiePayload):
    cookies_str = payload.cookies_str.strip()
    if not cookies_str or cookies_str == "your_cookies_here":
        raise HTTPException(status_code=400, detail="cookie 不能为空")
    if not trans_cookies(cookies_str).get("unb"):
        raise HTTPException(status_code=400, detail="cookie 中缺少 unb 字段（用户ID），请复制闲鱼网页版完整的 Cookie")
    _apply_cookie(cookies_str)
    return {"ok": True, "is_set": True, "cookie_masked": _mask_cookie(cookies_str)}


@app.get("/api/cookie/auto/status")
def auto_connect_status():
    return dict(_auto_state)


@app.post("/api/cookie/auto")
def auto_connect():
    with _auto_lock:
        if _auto_state["running"]:
            raise HTTPException(status_code=409, detail="自动连接已在进行中")
        _auto_state.update(running=True, done=False, ok=False, message="准备启动浏览器…")

    def _run():
        try:
            from get_cookie import fetch_cookie_via_edge

            def _progress(s: str):
                _auto_state["message"] = s

            cookie_str = fetch_cookie_via_edge(progress=_progress)
            if not cookie_str:
                _auto_state.update(running=False, done=True, ok=False, message="未获取到 Cookie，请重试")
                return
            _apply_cookie(cookie_str)
            _auto_state.update(running=False, done=True, ok=True, message="已保存 Cookie 并重连闲鱼")
        except Exception as e:
            logger.error(f"自动连接异常: {e}")
            _auto_state.update(running=False, done=True, ok=False, message=f"自动连接失败: {e}")

    threading.Thread(target=_run, daemon=True).start()
    return {"ok": True, "started": True}


@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


# 静态资源（放在所有 API 路由之后）
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
