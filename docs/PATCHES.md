# 补丁说明（对第三方组件做的修改）

本项目对上游组件做了若干本地修改，记录在此以便复现。所有补丁都在**真机验证过**，原因见 `BUILD-NOTES.md`。

## 1. MaiBot-SnowLuma-Adapter 补丁

### 1.1 QQ 表情名转换边界修复
`codecs/outbound/segment_encoder.py`

- **问题**：`「呜/捂脸麦麦错怪哥哥」` 这类句中表情不转换，`/捂脸` 原样发到 QQ。
- **原因**：转换正则的后随边界用了 `(?!\w)`，而 Python 的 `\w` 包含汉字，表情名后紧跟汉字时被判为非表情。
- **修复**：改为 `(?![A-Za-z0-9_])`，只挡英文/数字/下划线。

### 1.2 表情别名表
`qq_face_map.py`

模型常用的表情名（B 站梗图名）在 QQ 经典黄脸表里不存在，会原样漏字。加了别名映射：

| 模型写的 | 实际发出 |
|---|---|
| /滑稽 | 😁 呲牙 |
| /哭 | 😭 大哭 |
| /伤心 | 难过 |
| /震惊 | 惊讶 |
| /加油 | 鼓掌 |
| /翻白眼 | 白眼 |
| /吐血 | 汗 |
| /大惊 | 惊恐 |
| /羡慕 | 崇拜 |
| /心疼 | 拍头 |
| /馋 | 吃 |

### 1.3 英文字母颜文字出站过滤
`codecs/outbound/segment_encoder.py`

- **问题**：人设明确禁止 `awa/qwq/owo`，但回复模型仍会输出（提示词约束不可靠）。
- **修复**：出站文本物理剥离黑名单 `awa|qwq|owo|ovo|uwu|qaq|030|0v0|ono|oto|ata|>_<`（含连写），符号颜文字如 `(๑•̀ㅂ•́)و✧` 不受影响；正常英文词 `ok/QQ` 不误伤。

### 1.4 出站安全过滤（新增模块）
`services/security_filter.py` + `services/action_service.py`

在所有发送动作前检查消息文本，命中以下特征则**整条拦截**：
- 本机路径：`C:\...`、`/home/...`、`file://`、`base64://`
- 凭据：`ak-*`、`sk-*`、`Bearer *`、JWT
- 已知密钥字面量

语音消息走 `record` 段不吃文本过滤，因此 `maimai-voice` 插件内对 TTS 文本做了同源自查（见插件代码 `_find_violation`）。

## 2. MaiBot 核心补丁

### 2.1 消息渲染带 QQ 号（认人）
`src/maisaka/context/planner_messages.py`

- **问题**：聊天记录渲染成 `user="昵称"`，模型看不出谁是主人（哥哥），会乱叫「哥哥」。
- **修复**：`user_name` 改为 `昵称(QQ号)` 格式：

```python
user_name = user_info.user_nickname or user_info.user_id
if user_info.user_nickname and user_info.user_id and str(user_info.user_id) != str(user_info.user_nickname):
    user_name = f"{user_info.user_nickname}({user_info.user_id})"
```

### 2.2 send_emoji 占位图透明通道
`src/maisaka/builtin_tool/send_emoji.py`

- **问题**：表情包池里有损坏 JPEG 时，占位图以 RGB 模式粘贴到 RGBA 画布，`ValueError: bad transparency mask` 导致整条表情发送失败。
- **修复**：占位图改为 RGBA 绘制。

## 3. A_Memorix 存储路径

- **问题**：faiss 的 C++ 层用 `fopen`，**不支持中文路径**，`D:\code2\AI伙伴\...` 下写索引报 `No such file or directory`。
- **修复**：`[a_memorix.storage] data_dir` 指向纯英文路径（如 `D:/code2/maibot-memory`）。

> 同类坑：RVC 的 `.index` 文件（faiss 读取）也必须在英文路径下。

## 4. GPT-SoVITS Windows 适配

- `pyopenjtalk` / `jieba_fast` 需 MSVC 编译 → 写 shim：`jieba_fast` 转发 `jieba`，`pyopenjtalk` 桩（中文合成不依赖日文 g2p）
- `fast-langdetect` 需要缓存目录 → 建 `GPT_SoVITS/pretrained_models/fast_langdetect` 后自动下载 125MB 语言模型
- HF 下载 SSL 失败 → `truststore.inject_into_ssl()` 接系统证书库；`HF_HUB_DISABLE_XET=1` 关掉 xet 存储后端
