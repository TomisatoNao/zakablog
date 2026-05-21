"""全局配置、路径、环境变量、日志初始化。"""
import os
import sys
import json
import logging
from logging.handlers import RotatingFileHandler
from datetime import timezone, timedelta
from pathlib import Path

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env", override=False)
except ImportError:
    pass

# ── 终端颜色 ─────────────────────────────────
USE_COLOR = sys.stdout.isatty()
def _c(code: str) -> str: return code if USE_COLOR else ""

RESET   = _c("\033[0m")
BOLD    = _c("\033[1m")
DIM     = _c("\033[2m")
C_TIME  = _c("\033[36m")
C_INFO  = _c("\033[32m")
C_WARN  = _c("\033[33m")
C_ERR   = _c("\033[31m")
C_DEBUG = _c("\033[90m")
C_NEW   = _c("\033[35m")
C_SLEEP = _c("\033[34m")

LEVEL_STYLES = {
    "DEBUG":    f"{C_DEBUG}DEBUG{RESET}",
    "INFO":     f"{C_INFO}INFO {RESET}",
    "WARNING":  f"{C_WARN}WARN {RESET}",
    "ERROR":    f"{C_ERR}{BOLD}ERROR{RESET}",
    "CRITICAL": f"{C_ERR}{BOLD}CRIT {RESET}",
}

class PrettyFormatter(logging.Formatter):
    def format(self, record):
        ts    = self.formatTime(record, "%H:%M:%S")
        level = LEVEL_STYLES.get(record.levelname, record.levelname)
        return f"{C_TIME}{ts}{RESET} {level} {record.getMessage()}"

# ── 日志 ─────────────────────────────────────
_console_handler = logging.StreamHandler(sys.stdout)
_console_handler.setFormatter(PrettyFormatter())

_log_dir = ROOT / "logs"
_log_dir.mkdir(exist_ok=True)
_file_handler = RotatingFileHandler(
    _log_dir / "blog.log", encoding="utf-8", maxBytes=10 * 1024 * 1024, backupCount=5
)
_file_handler.setLevel(logging.INFO)
_file_handler.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)-8s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
))

logging.basicConfig(level=logging.INFO, handlers=[_console_handler, _file_handler])

# ── 路径 ─────────────────────────────────────
SAVE_DIR    = ROOT / "blog_images"
RECORD_FILE = ROOT / "data" / "blog_records.json"
BLACKLIST_FILE = ROOT / "data" / "blacklist.json"
QQ_API_BASE = "https://api.sgroup.qq.com"

# ── Bot 配置 ─────────────────────────────────
def _load_bots() -> list[dict]:
    bots = []
    keys = ["hinatazaka", "nogizaka", "sakurazaka"]
    for i in range(1, 5):
        app_id = os.getenv(f"BOT{i}_APP_ID", "").strip()
        secret = os.getenv(f"BOT{i}_CLIENT_SECRET", "").strip()
        openid = os.getenv(f"BOT{i}_TARGET_OPENID", "").strip()
        if app_id and secret and openid:
            groups = {}
            for k in keys:
                env_k = f"BOT{i}_{k.upper()}_ENABLED"
                groups[k] = os.getenv(env_k, "true").lower() != "false"
            bots.append({
                "name": f"Bot {i}",
                "app_id": app_id,
                "client_secret": secret,
                "target_openid": openid,
                "groups": groups,
            })
    return bots

BOTS = _load_bots()

# ── 黑名单 ───────────────────────────────────
def _load_blacklist() -> dict[str, set[str]]:
    """返回 {key: set(authors)}。
    key: 'global', 'Bot 1'..'Bot 4', 'tg.hinatazaka', 'tg.nogizaka', 'tg.sakurazaka'
    兼容旧格式：纯数组自动转为 global。
    """
    empty = {"global": set()}
    if not os.path.exists(BLACKLIST_FILE):
        return empty
    try:
        with open(BLACKLIST_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        log.warning("黑名单文件读取失败: %s", e)
        return empty
    if isinstance(data, list):
        return {"global": set(data)}
    if not isinstance(data, dict):
        return empty
    result = {"global": set(data.get("global", []))}
    for i in range(1, 5):
        result[f"Bot {i}"] = set(data.get(f"Bot {i}", []))
    tg = data.get("tg", {}) if isinstance(data.get("tg"), dict) else {}
    for k in ("hinatazaka", "nogizaka", "sakurazaka"):
        result[f"tg.{k}"] = set(tg.get(k, []))
    return result

BLACKLIST = _load_blacklist()


def get_blacklist(bot_name: str = "", tg_group: str = "") -> set[str]:
    """返回指定通道的生效黑名单：global + 对应 Bot/TG 名单。"""
    s = set(BLACKLIST.get("global", set()))
    if bot_name:
        s.update(BLACKLIST.get(bot_name, set()))
    if tg_group:
        s.update(BLACKLIST.get(f"tg.{tg_group}", set()))
    return s

# ── 平台开关 ─────────────────────────────────
QQ_ENABLED = os.getenv("QQ_ENABLED", "true").lower() != "false"
TG_ENABLED  = os.getenv("TG_ENABLED", "false").lower() == "true"

# ── Telegram 坂道配置 ────────────────────────
def _load_tg_groups() -> dict:
    groups = {}
    for key, label in [("hinatazaka", "HINATA"), ("nogizaka", "NOGI"), ("sakurazaka", "SAKURA")]:
        enabled = os.getenv(f"TG_{label}_ENABLED", "true").lower() == "true"
        token   = os.getenv(f"TG_{label}_BOT_TOKEN", "").strip()
        chat_id = os.getenv(f"TG_{label}_CHAT_ID", "").strip()
        groups[key] = {"enabled": enabled, "token": token, "chat_id": chat_id}
    return groups

TG_GROUPS = _load_tg_groups()

# ── 可调参数 ─────────────────────────────────
IMAGE_SEND_DELAY = 1.5
BOT_SWITCH_DELAY = 3.0
MAX_IMAGE_DIR_GB = 5
MAX_IMAGE_MB     = 20
MAX_RETRIES      = 3
DAY_MIN   = 150
DAY_MAX   = 210
NIGHT_MIN = 1650
NIGHT_MAX = 1950

JST = timezone(timedelta(hours=9))
