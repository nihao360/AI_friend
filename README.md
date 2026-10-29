# 麦麦 · QQ AI 妹妹（MaiBot + SnowLuma）

一个部署在 Windows 上的 QQ 虚拟人项目：**麦麦**，6 岁的 AI 妹妹，运行在自己的备用 QQ 号上，陪哥哥（主人账号）聊天、发表情包、发语音、主动说话、写日记。

> 本项目是把 [MaiBot](https://github.com/Mai-with-u/MaiBot)（大脑）+ [SnowLuma](https://github.com/SnowLuma/SnowLuma)（QQ 协议端）组合起来后的**完整部署与自研插件集合**。

## 架构

```
QQ 客户端（备用号，hook 注入）
      ↕
SnowLuma 协议端（HTTP 3100 / WebSocket 3101 / WebUI 5099）
      ↕
MaiBot-SnowLuma-Adapter（适配器，含表情转换/出站安全过滤）
      ↕
MaiBot 核心（WebUI 8001）
  ├── 规划器（DeepSeek V4 Flash）：决定回不回、发表情、发语音
  ├── 回复器 / 表情选择 / 记忆（A_Memorix 向量记忆）
  └── 插件
      ├── maimai-voice      语音发送（GPT-SoVITS + RVC 大肥鱼音色）
      ├── maimai-proactive  随机主动聊天（35-75 分钟随机醒来掷骰子）
      └── better-diary      睡前日记（生成后发 QQ 空间）
      ↕
本地语音栈（E:\ai-voice）
  ├── GPT-SoVITS v2Pro   TTS 零样本克隆（9881）
  ├── Applio (RVC)       大肥鱼音色转换（9880 聚合服务）
  └── fastembed bge-zh   记忆向量化（9890）
```

## 功能特性

| 能力 | 说明 |
|---|---|
| 🎀 人设 | 6 岁小妹妹：短句、叠词、不用英文字母颜文字（awa/qwq 被物理过滤），只认一个哥哥 |
| 😂 表情包 | 自主选图发送；`/呲牙` 式 QQ 黄脸表情支持；未知表情名自动映射（滑稽→呲牙、心疼→拍头等） |
| 🎤 语音 | GPT-SoVITS 零样本克隆 + RVC 大肥鱼音色，热延迟约 1.4-3 秒；被要求唱歌会承认五音不全 |
| 💬 主动聊天 | 不设固定时段，35-75 分钟随机醒来、30% 概率想说话；别人在聊天时安静 |
| 📔 日记 | 每晚 23:30 把当天聊天写成日记发 QQ 空间 |
| 🧠 记忆 | A_Memorix 长期记忆 + 本地 512 维中文嵌入（bge-small-zh），语义检索 |
| 🔒 出站安全 | 适配器拦截含本机路径/凭据的消息；语音绕过文本过滤时插件内再查一遍 |

## 目录结构

```
├── start-all.ps1 / .cmd     一键启动（QQ → SnowLuma → 语音栈 → MaiBot）
├── stop-all.ps1 / .cmd      一键停止
├── config/                  配置模板（已脱敏，需自行填入密钥）
│   ├── bot_config.toml      人格/发言频率/记忆/主动聊天配置
│   └── model_config.toml    模型与服务商配置（DeepSeek / 讯飞 MaaS / 本地嵌入）
├── plugins/
│   ├── maimai-voice/        语音插件（send_voice 工具 + RVC 服务调用）
│   └── maimai-proactive/    主动聊天插件（随机游走调度）
├── voice/
│   ├── voice-server.py      语音聚合服务（TTS → 可选 RVC → wav，9880）
│   ├── embedding-server.py  本地嵌入服务（OpenAI 兼容 /v1/embeddings，9890）
│   └── voice-config.json    语音引擎配置（gsv/edge、是否串联 RVC）
└── docs/
    ├── BUILD-NOTES.md       部署踩坑记录（黑屏/端口/路径/依赖全记录）
    └── PATCHES.md           对适配器与核心的补丁说明
```

## 快速开始

1. 安装 [MaiBot](https://github.com/Mai-with-u/MaiBot) 与 [SnowLuma](https://github.com/SnowLuma/SnowLuma)，按各自文档配好
2. 把 `plugins/maimai-voice`、`plugins/maimai-proactive` 复制进 `maibot/plugins/`
3. 复制 `config/*.toml` 到 `maibot/config/`，填入你的 API 密钥与 QQ 号
4. 语音栈（可选）：按 `docs/BUILD-NOTES.md` 的步骤装 GPT-SoVITS + Applio + RVC 音色模型
5. 双击 `start-all.cmd`

## 环境要求

- Windows 10/11（实测 RTX 5070 12GB）
- Python 3.10（GPT-SoVITS）/ 3.12（语音服务）/ 3.13（MaiBot 自带环境）
- PyTorch 2.7.1+cu128 或 2.11.0+cu128（RTX 50 系 Blackwell 必须 cu128）

## 安全说明

- 仓库内所有密钥、令牌、QQ 号均已脱敏为占位符（`YOUR_XXX`），**使用前必须替换**
- 真实凭据不要提交进 git；建议用环境变量或私有配置文件（见 `.gitignore`）
- `maibot/data`、`logs`、模型文件、`node.exe` 等大体积/隐私内容不纳入仓库

## 致谢

- [MaiBot](https://github.com/Mai-with-u/MaiBot) · [MaiBot-SnowLuma-Adapter](https://github.com/Mai-with-u/MaiBot-SnowLuma-Adapter)
- [SnowLuma](https://github.com/SnowLuma/SnowLuma)
- [GPT-SoVITS](https://github.com/RVC-Boss/GPT-SoVITS) · [Applio](https://github.com/IAHispano/Applio)（RVC）
- 大肥鱼/飞鱼音色：`YukiKaze1337/DaFeiYu_rvc_v2_40k`、`Esmerubphire/FeiyuVoice-*`（训练素材由 B 站 UP 主授权，见各自 NOTICE）
- [A_Memorix](https://github.com/...) · [better-diary](https://github.com/orge-8/better-diary)

## License

自研部分（`plugins/maimai-*`、`voice/`、脚本）MIT。第三方组件遵循其各自许可证。
