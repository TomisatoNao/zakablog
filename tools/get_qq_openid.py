"""临时工具：通过 WebSocket 监听 QQ Bot 事件，获取用户 openid。

用法：
    python tools/get_qq_openid.py

前置条件：
    1. .env 中已配置 BOT1_APP_ID 和 BOT1_CLIENT_SECRET
    2. pip install httpx websockets

工作原理：
    1. 读取 Bot 凭证，获取 access_token
    2. 通过 WebSocket 连接 QQ 网关（长连接模式）
    3. 用户给机器人发一条私聊消息
    4. 脚本捕获 C2C_MESSAGE_CREATE 事件，打印其中的 openid
    5. 将 openid 填入 .env 的 BOT1_TARGET_OPENID 即可
"""

import asyncio
import json
import os
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from config import BOTS, QQ_API_BASE

TOKEN_URL = "https://bots.qq.com/app/getAppAccessToken"
GROUP_AND_C2C_EVENT_INTENT = 1 << 25


def _find_openid_values(obj, path=""):
    """递归搜索 JSON 中所有 openid 相关字段。"""
    found = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            next_path = f"{path}.{key}" if path else key
            if "openid" in key.lower() and isinstance(value, str):
                found.append((next_path, value))
            found.extend(_find_openid_values(value, next_path))
    elif isinstance(obj, list):
        for i, value in enumerate(obj):
            found.extend(_find_openid_values(value, f"{path}[{i}]"))
    return found


async def _get_access_token(client, bot_index: int = 0) -> str:
    if not BOTS or bot_index >= len(BOTS):
        raise RuntimeError("请先在 .env 中配置 QQ Bot（BOT1_APP_ID 等）")

    bot = BOTS[bot_index]
    print(f"使用 [{bot['name']}] 获取 access_token ...")

    resp = await client.post(
        TOKEN_URL,
        json={"appId": bot["app_id"], "clientSecret": bot["client_secret"]},
        headers={"Content-Type": "application/json"},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    token = data.get("access_token")
    if not token:
        raise RuntimeError(f"token 响应中没有 access_token: {data}")
    return token


async def _get_gateway_url(client, token: str) -> str:
    headers = {"Authorization": f"QQBot {token}"}
    resp = await client.get(f"{QQ_API_BASE}/gateway", headers=headers, timeout=15)
    if resp.status_code != 200:
        resp = await client.get(f"{QQ_API_BASE}/gateway/bot", headers=headers, timeout=15)
    if resp.status_code != 200:
        raise RuntimeError(f"获取网关地址失败: HTTP {resp.status_code}: {resp.text[:200]}")
    data = resp.json()
    gateway_url = data.get("url")
    if not gateway_url:
        raise RuntimeError(f"网关响应中没有 url: {data}")
    return gateway_url


async def _heartbeat(ws, interval_ms: int, seq_ref: dict):
    interval = max(interval_ms / 1000, 1)
    while True:
        await asyncio.sleep(interval)
        await ws.send(json.dumps({"op": 1, "d": seq_ref.get("seq")}))


async def main():
    try:
        import httpx
        import websockets
    except ImportError as e:
        raise RuntimeError(
            f"缺少依赖: {e}\n请运行: pip install httpx websockets"
        )

    if not BOTS:
        raise RuntimeError("未配置任何 QQ Bot，请在 .env 中设置 BOT1_APP_ID 等变量")

    # 列出可用 Bot
    print("可用的 QQ Bot：")
    for i, bot in enumerate(BOTS):
        print(f"  [{i}] {bot['name']} (app_id: {bot['app_id'][:4]}****)")

    bot_index = 0
    if len(BOTS) > 1:
        choice = input(f"\n选择 Bot 序号 [0-{len(BOTS)-1}]，默认 0: ").strip()
        if choice and choice.isdigit():
            bot_index = int(choice)

    async with httpx.AsyncClient() as client:
        token = await _get_access_token(client, bot_index)
        gateway_url = await _get_gateway_url(client, token)

    print("已获取网关地址，正在连接 WebSocket ...")
    print("连接成功后，请用你的 QQ 私聊机器人发一句话。")
    print("按 Ctrl+C 退出。\n")

    seq_ref = {"seq": None}
    async with websockets.connect(gateway_url) as ws:
        hello = json.loads(await ws.recv())
        interval_ms = hello.get("d", {}).get("heartbeat_interval", 45000)
        heartbeat_task = asyncio.create_task(_heartbeat(ws, interval_ms, seq_ref))

        identify = {
            "op": 2,
            "d": {
                "token": f"QQBot {token}",
                "intents": GROUP_AND_C2C_EVENT_INTENT,
                "shard": [0, 1],
                "properties": {
                    "$os": "windows",
                    "$browser": "zakablog-openid-helper",
                    "$device": "zakablog-openid-helper",
                },
            },
        }
        await ws.send(json.dumps(identify))

        try:
            while True:
                raw = await ws.recv()
                event = json.loads(raw)
                if "s" in event and event["s"] is not None:
                    seq_ref["seq"] = event["s"]

                event_type = event.get("t")
                if event.get("op") == 11:  # Heartbeat ACK，静默
                    continue

                print(f"\n{'=' * 50}")
                event_desc = event_type if event_type else f"op={event.get('op')}"
                print(f"收到事件: {event_desc}")

                openids = _find_openid_values(event)
                if openids:
                    print(f"\n找到 openid：")
                    for path, value in openids:
                        print(f"  {path} = {value}")
                    print(f"\n请将以下内容添加到 .env 文件中：")
                    bot_var_prefix = BOTS[bot_index]["name"].replace(" ", "_").upper()
                    print(f"  {bot_var_prefix}_TARGET_OPENID={openids[0][1]}")
                    print(f"\n继续监听中，如已拿到 openid 可按 Ctrl+C 退出。")
                else:
                    print("(未检测到 openid，打印完整事件内容)")
                    print(json.dumps(event, ensure_ascii=False, indent=2))
        finally:
            heartbeat_task.cancel()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n已退出。")
    except Exception as e:
        print(f"\n运行失败: {type(e).__name__}: {e}")
