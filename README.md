# 🌸 坂道联合博客监控

日向坂46 / 乃木坂46 / 樱坂46 新博客自动监控，通过 QQ Bot / Telegram Bot 实时推送通知和图片。

## 功能

- 同时监控三个坂道团体（日向坂46、乃木坂46、樱坂46）的官方博客
- 检测到新博客时自动下载全部图片到本地
- 通过 QQ Bot / Telegram Bot 双平台推送通知和图片
- 自适应巡检频率：日间 2.5~3.5 分钟，夜间 27.5~32.5 分钟（JST）
- 终端彩色状态面板，实时展示各坂道最新博客
- 日志自动轮转（10MB × 5 个备份）
- 支持多 Bot 同时推送（最多 4 个）
- 作者黑名单静默跳过

## 支持的博客源

| 团体 | 站点 | 抓取方式 |
|---|---|---|
| 日向坂46 | hinatazaka46.com | HTML 列表页解析 |
| 乃木坂46 | nogizaka46.com | JSONP API |
| 樱坂46 | sakurazaka46.com | HTML 列表页 + 详情页解析 |

## 环境要求

- Python 3.10+
- 可访问 QQ Bot API（`api.sgroup.qq.com`、`bots.qq.com`）

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置 Bot
# 复制模板文件并填入真实值
cp .env.example .env
# 然后用文本编辑器编辑 .env 文件，填入真实密钥

# .env 文件已被 .gitignore 忽略，不会被提交到 Git
# 如果同时设置了系统环境变量和 .env，系统环境变量优先
# Linux / macOS
export BOT1_APP_ID="your_app_id"
export BOT1_CLIENT_SECRET="your_client_secret"
export BOT1_TARGET_OPENID="your_target_openid"

# Windows PowerShell
$env:BOT1_APP_ID = "your_app_id"
$env:BOT1_CLIENT_SECRET = "your_client_secret"
$env:BOT1_TARGET_OPENID = "your_target_openid"

# 3. 启动监控
python blog.py
```

### 获取 QQ Bot OpenID（首次配置）

如果不知道 `TARGET_OPENID`，可使用内置工具通过 WebSocket 监听获取：

```bash
# 先确保 .env 中已填入 APP_ID 和 CLIENT_SECRET
pip install httpx websockets
python tools/get_qq_openid.py
```

然后用你的 QQ 私聊机器人发一条消息，终端会打印出你的 openid，填入 `.env` 即可。

## 平台开关

| 变量 | 默认 | 说明 |
|---|---|---|
| `QQ_ENABLED` | true | QQ Bot 总开关 |
| `TG_ENABLED` | false | Telegram Bot 总开关 |

## 环境变量

可通过 `.env` 文件或系统环境变量配置，**系统环境变量优先级高于 `.env`**。

### QQ Bot

| 变量 | 说明 | 必填 |
|---|---|---|
| `BOT1_APP_ID` | Bot 1 的 App ID | 是（至少配置一个） |
| `BOT1_CLIENT_SECRET` | Bot 1 的 Client Secret | 是 |
| `BOT1_TARGET_OPENID` | Bot 1 推送目标的 OpenID | 是 |
| `BOT1_HINATA_ENABLED` | Bot 1 是否推送日向坂（默认 true） | 否 |
| `BOT1_NOGI_ENABLED` | Bot 1 是否推送乃木坂（默认 true） | 否 |
| `BOT1_SAKURA_ENABLED` | Bot 1 是否推送樱坂（默认 true） | 否 |
| `BOT2_APP_ID` ~ `BOT4_APP_ID` | 更多 Bot（可选） | 否 |

每个 Bot 可独立控制三个坂道的推送开关。Bot 按序号依次推送，Bot 之间有 3 秒间隔避免触发频率限制。

### Telegram Bot

通过 @BotFather 创建 Bot，每个坂道独立配置（可填相同的 token 共用同一个 Bot）。

| 变量 | 说明 | 必填 |
|---|---|---|
| `TG_HINATA_ENABLED` | 日向坂 Telegram 推送开关（默认 true） | 否 |
| `TG_HINATA_BOT_TOKEN` | 日向坂 Telegram Bot Token | 按需 |
| `TG_HINATA_CHAT_ID` | 日向坂推送目标（频道/群组 ID） | 按需 |
| `TG_NOGI_ENABLED` | 乃木坂 Telegram 推送开关（默认 true） | 否 |
| `TG_NOGI_BOT_TOKEN` | 乃木坂 Telegram Bot Token | 按需 |
| `TG_NOGI_CHAT_ID` | 乃木坂推送目标 | 按需 |
| `TG_SAKURA_ENABLED` | 樱坂 Telegram 推送开关（默认 true） | 否 |
| `TG_SAKURA_BOT_TOKEN` | 樱坂 Telegram Bot Token | 按需 |
| `TG_SAKURA_CHAT_ID` | 樱坂推送目标 | 按需 |

图片以媒体组方式发送（≤10 张/组，超过自动拆组）。

## 配置说明

在 `config.py` 中可直接修改以下参数：

| 参数 | 默认值 | 说明 |
|---|---|---|
| `DAY_MIN` / `DAY_MAX` | 150 / 210 秒 | 日间巡检间隔范围 |
| `NIGHT_MIN` / `NIGHT_MAX` | 1650 / 1950 秒 | 夜间巡检间隔范围 |
| `IMAGE_SEND_DELAY` | 1.5 秒 | 单张图片发送间隔 |
| `BOT_SWITCH_DELAY` | 3.0 秒 | 多 Bot 切换间隔 |
| `BLACKLIST_FILE` | `./blacklist.json` | 黑名单文件路径，JSON 字符串数组 |
| `MAX_IMAGE_DIR_GB` | 0 | 图片目录容量上限（GB），超限整目录删除，0 = 不限制 |
| `MAX_IMAGE_MB` | 20 | 单张图片大小上限（MB），超限跳过 |
| `QQ_ENABLED` / `TG_ENABLED` | true / false | 平台总开关 |
| `MAX_RETRIES` | 3 | 网络请求失败重试次数 |

## 项目结构

```
zakablog/
├── blog.py                 # 启动入口
├── main.py                 # 主调度（面板、巡检编排、主循环）
├── config.py               # 全局配置、路径、环境变量、日志初始化
├── core/                   # 共享工具模块
│   ├── network.py          #   HTTP 请求（GET/POST）与 JSONP 解析
│   └── storage.py          #   状态持久化、图片下载与清理
├── bots/                   # 通知推送模块
│   ├── qq_bot.py           #   QQ Bot：Token 缓存、文字/图片推送
│   └── tg_bot.py           #   Telegram Bot：文本/媒体组推送
├── sources/                # 博客源抓取模块
│   ├── hinatazaka.py       #   日向坂46
│   ├── nogizaka.py         #   乃木坂46
│   └── sakurazaka.py       #   樱坂46
├── tools/                  # 辅助工具
│   └── get_qq_openid.py    #   QQ Bot openid 获取工具
├── data/                   # 运行时数据（自动生成）
│   ├── blog_records.json   #   各坂道已抓取的最新博客 URL
│   ├── blacklist.json      #   用户黑名单（可选）
│   └── blacklist.example.json  # 黑名单模板
├── logs/                   # 运行日志（自动轮转）
│   └── blog.log
├── blog_images/            # 下载的博客图片
├── .env.example            # 环境变量配置模板
├── .gitignore
└── requirements.txt        # Python 依赖
```

## 运行效果

启动后终端显示彩色状态面板：

```
══════════════════════════════════════════════════════
   🌸 坂道联合博客监控中心
   日向坂46 / 乃木坂46 / 樱坂46
──────────────────────────────────────────────────────
   状态   ● 运行中   第 42 轮   ☀️  日间模式
   时间   2026-05-11 14:23:15
──────────────────────────────────────────────────────
   本轮巡检
   [日向坂46] ✓ 无更新
   [乃木坂46] 📢 池田 瑛紗《水無月になれば薫る》
   [樱坂46] ✓ 无更新
──────────────────────────────────────────────────────
   最新博客
   ☀️ 日向  平尾 帆夏  《仲間とはぐれないように…》
   💜 乃木  池田 瑛紗  《水無月になれば薫る》
   🌸 樱坂  松田 里奈  《391》
──────────────────────────────────────────────────────
   💤 下次巡检：2分18秒 后（Ctrl+C 退出）
══════════════════════════════════════════════════════
```

按 `Ctrl+C` 随时退出。

## 注意事项

- 请勿将 `.env` 或包含真实密钥的文件提交到版本控制
- QQ Bot 需要预先在 [QQ 开放平台](https://q.qq.com) 创建应用并获取凭证
- 博客图片会持续累积，建议定期清理 `blog_images/` 目录
- 夜间模式判定基于 JST（UTC+9），不受服务器所在时区影响
