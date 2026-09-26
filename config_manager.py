"""多模型配置管理：读写 config.json，支持多家 API key 的增删改查与切换。"""
import json
import os
import uuid
import threading
from typing import List, Dict, Optional

from loguru import logger

# 项目根目录（与本文件同级）
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")

_lock = threading.RLock()


def _default_model_entry(api_key: str = "", base_url: str = "", model_name: str = "") -> Dict:
    """生成一条默认的通义千问模型条目。"""
    return {
        "id": str(uuid.uuid4())[:8],
        "provider": "通义千问(Qwen)",
        "api_key": api_key,
        "base_url": base_url or "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model_name": model_name or "qwen-max",
        "is_current": True,
    }


def _migrate_from_env() -> Optional[Dict]:
    """首次运行时，若 .env 里有旧的 API_KEY，则迁移为一条默认模型条目。"""
    try:
        # 延迟导入，避免与 dotenv 加载顺序耦合
        from dotenv import load_dotenv
        env_path = os.path.join(BASE_DIR, ".env")
        if os.path.exists(env_path):
            load_dotenv(env_path)
    except Exception:
        pass

    old_api_key = os.getenv("API_KEY", "").strip()
    placeholder = "默认使用通义千问,apikey通过百炼模型平台获取"
    if not old_api_key or old_api_key == placeholder or old_api_key == "your_cookies_here":
        return None

    old_base = os.getenv("MODEL_BASE_URL", "").strip()
    old_model = os.getenv("MODEL_NAME", "qwen-max").strip()
    logger.info("检测到 .env 中的旧 API_KEY，已迁移到 config.json")
    return _default_model_entry(old_api_key, old_base, old_model)


def load_config() -> Dict:
    """加载配置，若文件不存在则尝试迁移旧配置或返回空配置。"""
    with _lock:
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                if not isinstance(cfg.get("models"), list):
                    cfg["models"] = []
                return cfg
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"config.json 读取失败，使用空配置: {e}")
                return {"models": []}

        # 文件不存在：尝试从 .env 迁移
        migrated = _migrate_from_env()
        cfg = {"models": [migrated] if migrated else []}
        save_config(cfg)
        return cfg


def save_config(cfg: Dict) -> None:
    """保存配置到 config.json。"""
    with _lock:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)


def list_models() -> List[Dict]:
    """返回所有模型（不暴露完整 api_key，仅显示掩码）。"""
    cfg = load_config()
    result = []
    for m in cfg.get("models", []):
        item = dict(m)
        key = item.get("api_key", "")
        if key:
            item["api_key_masked"] = _mask_key(key)
        result.append(item)
    return result


def get_current_model() -> Optional[Dict]:
    """返回当前启用的模型（含完整 api_key）。"""
    cfg = load_config()
    for m in cfg.get("models", []):
        if m.get("is_current"):
            return m
    return None


def get_model_by_id(model_id: str) -> Optional[Dict]:
    cfg = load_config()
    for m in cfg.get("models", []):
        if m.get("id") == model_id:
            return m
    return None


def add_model(provider: str, api_key: str, base_url: str, model_name: str) -> Dict:
    cfg = load_config()
    entry = {
        "id": str(uuid.uuid4())[:8],
        "provider": provider,
        "api_key": api_key,
        "base_url": base_url,
        "model_name": model_name,
        "is_current": False,
    }
    # 首个模型自动设为当前
    if not cfg.get("models"):
        entry["is_current"] = True
    cfg.setdefault("models", []).append(entry)
    save_config(cfg)
    return entry


def update_model(model_id: str, provider: str, api_key: str, base_url: str, model_name: str) -> Optional[Dict]:
    cfg = load_config()
    for m in cfg.get("models", []):
        if m.get("id") == model_id:
            m["provider"] = provider
            m["base_url"] = base_url
            m["model_name"] = model_name
            # api_key 留空表示不修改
            if api_key:
                m["api_key"] = api_key
            save_config(cfg)
            return m
    return None


def delete_model(model_id: str) -> bool:
    cfg = load_config()
    models = cfg.get("models", [])
    new_models = [m for m in models if m.get("id") != model_id]
    if len(new_models) == len(models):
        return False
    # 如果删除的是当前模型，把第一个剩余模型设为当前
    was_current = any(m.get("id") == model_id and m.get("is_current") for m in models)
    cfg["models"] = new_models
    if was_current and new_models:
        new_models[0]["is_current"] = True
    save_config(cfg)
    return True


def set_current(model_id: str) -> Optional[Dict]:
    cfg = load_config()
    target = None
    for m in cfg.get("models", []):
        if m.get("id") == model_id:
            m["is_current"] = True
            target = m
        else:
            m["is_current"] = False
    if target is None:
        return None
    save_config(cfg)
    return target


def _mask_key(key: str) -> str:
    """API key 脱敏显示：仅保留前 4 位 + 后 4 位。"""
    if len(key) <= 8:
        return "****"
    return f"{key[:4]}****{key[-4:]}"


# ---------- 议价策略 / 行为开关（存于 config.json 的 bargain_strategy / behavior 键） ----------

DEFAULT_BARGAIN_STRATEGY = {
    "enabled": True,
    "max_discount_ratio": 0.10,  # 最大优惠比例（占商品价的 10%）
    "tiers": [
        {"round": 1, "ratio": 0.00},  # 首轮不让步，让买家先出价
        {"round": 2, "ratio": 0.03},
        {"round": 3, "ratio": 0.06},
        {"round": 4, "ratio": 0.10},  # 触底
    ],
}

DEFAULT_BEHAVIOR = {
    "auto_manual_on_negative": False,  # 买家强烈负面情绪时是否自动转人工接管
}


def get_bargain_strategy() -> Dict:
    """返回议价策略，缺失字段用默认值补齐。"""
    cfg = load_config()
    stored = cfg.get("bargain_strategy") or {}
    merged = dict(DEFAULT_BARGAIN_STRATEGY)
    merged.update(stored)
    if not stored.get("tiers"):
        merged["tiers"] = DEFAULT_BARGAIN_STRATEGY["tiers"]
    return merged


def save_bargain_strategy(strategy: Dict) -> Dict:
    """保存议价策略并返回。"""
    cfg = load_config()
    cfg["bargain_strategy"] = strategy
    save_config(cfg)
    return strategy


def get_behavior() -> Dict:
    """返回行为开关，缺失字段用默认值补齐。"""
    cfg = load_config()
    stored = cfg.get("behavior") or {}
    merged = dict(DEFAULT_BEHAVIOR)
    merged.update(stored)
    return merged


def save_behavior(behavior: Dict) -> Dict:
    """保存行为开关并返回。"""
    cfg = load_config()
    cfg["behavior"] = behavior
    save_config(cfg)
    return behavior
