"""出站安全过滤器：拦截包含本机路径或凭据特征的消息文本。

灵感来自 qq-bridge（Derpyu520）的回复审计硬拦截：agent 回复文本若包含
本机路径或凭据特征则整条拦截不发送。这里在适配器的 OneBot 动作咽喉
（QQActionService.call_action）做同样的事，防止麦麦把提示词或配置里
的秘密（API key、WebUI 密码、令牌）或者本机文件路径原样发到 QQ。

只扫描文本段（type=="text" 的 data.text），不扫描图片/文件段的
base64 或路径引用——表情包按本地路径发送是正常行为，不能误杀。
合并转发节点里的文本也会被递归扫描。

命中即抛 RuntimeError，整条动作被拒绝发送（与 qq-bridge 的整条拦截一致）。
"""

from __future__ import annotations

import re
from typing import Any, List, Mapping, Optional, Tuple

# 是否启用出站安全过滤（紧急逃生开关：改 False 后重启插件生效）。
OUTBOUND_SECURITY_FILTER_ENABLED = True

# 会发送消息文本的 OneBot 动作集合。
_SEND_ACTIONS = frozenset(
    {
        "send_msg",
        "send_group_msg",
        "send_private_msg",
        "send_group_forward_msg",
        "send_private_forward_msg",
        "send_forward_msg",
    }
)

# 高置信度危险特征：本机绝对路径。
_PATH_PATTERNS: Tuple[Tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"[A-Za-z]:\\(?:[^\s:*?\"<>|\r\n]{1,64}\\)+"), "Windows 本机路径"),
    (re.compile(r"/(?:home|Users|root|etc|var|opt|usr)/[\w.\-/]{1,64}"), "Unix 本机路径"),
    (re.compile(r"(?:file|base64)://"), "本地文件引用"),
)

# 高置信度凭据特征。
_CREDENTIAL_PATTERNS: Tuple[Tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bak-[0-9a-f]{32}\b"), "API key"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"), "API key"),
    (re.compile(r"\b(?:ghp|gho|github_pat)_[A-Za-z0-9]{20,}\b"), "GitHub 令牌"),
    (re.compile(r"\bBearer\s+[A-Za-z0-9_.\-/+=]{16,}"), "Bearer 令牌"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\."), "JWT 令牌"),
)

# 本部署已知的具体密钥/令牌字面量（部分前缀匹配即可）。
_KNOWN_SECRETS: Tuple[str, ...] = (
    "YOUR_SNOWLUMA_WEBUI_PASSWORD",  # SnowLuma WebUI 密码
    "YOUR_SNOWLUMA_WS_TOKEN",  # OneBot WS accessToken
    "ak-YOUR_XFYUN_APP_KEY",  # 讯飞 MaaS API key
    "YOUR_MAIBOT_WEBUI_PASSWORD",  # MaiBot WebUI token
    "YOUR_ONEBOT_HTTP_TOKEN",  # QZone 令牌
)


def _extract_text_segments(value: Any, sink: List[str], depth: int = 0) -> None:
    """递归提取消息树里所有文本段的内容。"""

    if depth > 8:
        return
    if isinstance(value, Mapping):
        if value.get("type") == "text":
            data = value.get("data")
            if isinstance(data, Mapping):
                text = data.get("text")
                if isinstance(text, str) and text:
                    sink.append(text)
        for child in value.values():
            _extract_text_segments(child, sink, depth + 1)
    elif isinstance(value, (list, tuple)):
        for child in value:
            _extract_text_segments(child, sink, depth + 1)


def inspect_outbound_action(action_name: str, params: Mapping[str, Any]) -> Optional[str]:
    """检查发送动作的文本段是否包含危险特征。

    Args:
        action_name: OneBot 动作名。
        params: 动作参数。

    Returns:
        命中时返回违规原因描述；安全时返回 ``None``。
    """

    if not OUTBOUND_SECURITY_FILTER_ENABLED:
        return None
    if action_name not in _SEND_ACTIONS:
        return None
    if not isinstance(params, Mapping):
        return None

    texts: List[str] = []
    _extract_text_segments(params.get("message"), texts)
    _extract_text_segments(params.get("messages"), texts)
    if not texts:
        return None

    for text in texts:
        for pattern, label in _PATH_PATTERNS:
            if pattern.search(text):
                matched = pattern.search(text)
                return f"出站安全过滤：消息文本含{label}（{matched.group(0)[:48]!r}），已整条拦截"
        for pattern, label in _CREDENTIAL_PATTERNS:
            matched = pattern.search(text)
            if matched:
                return f"出站安全过滤：消息文本含{label}（{matched.group(0)[:12]!r}…），已整条拦截"
        for secret in _KNOWN_SECRETS:
            if secret in text:
                return f"出站安全过滤：消息文本含已知密钥特征（{secret[:8]!r}…），已整条拦截"
    return None
