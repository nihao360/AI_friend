# -*- coding: utf-8 -*-
"""maimai-voice：麦麦的语音发送插件。

设计（对齐 MaiBot「自主决定」哲学）：send_voice 是规划器可调用的工具，
和 send_emoji 一样由麦麦自己判断什么时候用——撒娇、道晚安、唱歌、
情绪强烈到文字不够的时候。工具内部做四道防御：

1. 长度上限：语音要短（默认 80 字内），长了拒绝并提示改用文字；
2. 冷却：同一聊天流默认 90 秒一条，防刷屏（QQ 对语音消息也限频）；
3. 内容检查：先过本机路径/凭据特征（与 SnowLuma 适配器出站过滤同源规则），
   语音绕过文本出站过滤，必须在这里补一道；
4. TTS 失败降级：网络问题不炸工具，明确告知规划器可改用文字。
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional

from maibot_sdk import Field, MaiBotPlugin, PluginConfigBase, Tool

logger = logging.getLogger("plugin.local.maimai-voice")

# 唱歌曲库：预先渲染好的派蒙音色儿歌（真唱，UVR 分离 + RVC 换音色）
SONG_DIR = r"E:\ai-voice\sing\cache"


def _load_song_index() -> List[Dict[str, Any]]:
    """读取曲库索引 index.json，返回歌曲列表；读不到返回空列表。"""

    path = os.path.join(SONG_DIR, "index.json")
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as exc:
        logger.warning("读取唱歌曲库失败: %s", exc)
        return []
    songs = data.get("songs") if isinstance(data, dict) else None
    return [s for s in songs if isinstance(s, dict)] if isinstance(songs, list) else []


class PluginSection(PluginConfigBase):
    """插件节。"""

    enabled: bool = Field(default=True, description="插件开关")
    config_version: str = Field(default="1.0.0", description="配置版本")


class VoiceSection(PluginConfigBase):
    """语音节。"""

    engine: str = Field(default="rvc", description="语音引擎：rvc=本地大肥鱼音色服务 / edge=原版 edge-tts")
    rvc_service_url: str = Field(default="http://127.0.0.1:9880/tts", description="RVC 语音服务地址")
    voice_name: str = Field(default="zh-CN-XiaoyiNeural", description="Edge-TTS 声线名（edge 引擎用）")
    rate: str = Field(default="+4%", description="语速调整（edge 引擎用）")
    pitch: str = Field(default="+12Hz", description="音调调整（edge 引擎用）")
    max_chars: int = Field(default=80, description="单条语音文本上限（字）")
    cooldown_seconds: int = Field(default=90, description="同一聊天流的语音冷却（秒）")
    sing_cooldown_seconds: int = Field(default=180, description="同一聊天流唱歌的冷却（秒）")


class MaimaiVoiceConfig(PluginConfigBase):
    """插件配置总模型。"""

    plugin: PluginSection = Field(default_factory=PluginSection)
    voice: VoiceSection = Field(default_factory=VoiceSection)


# 与适配器出站安全过滤同源的危险特征（语音不吃文本过滤，这里补一道）
_PATH_PATTERNS = (
    re.compile(r"[A-Za-z]:\\(?:[^\s:*?\"<>|\r\n]{1,64}\\)+"),
    re.compile(r"/(?:home|Users|root|etc|var|opt|usr)/[\w.\-/]{1,64}"),
)
_CREDENTIAL_PATTERNS = (
    re.compile(r"\bak-[0-9a-f]{32}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9_.\-/+=]{16,}"),
)
_KNOWN_SECRETS = (
    "YOUR_SNOWLUMA_WEBUI_PASSWORD",
    "YOUR_SNOWLUMA_WS_TOKEN",
    "ak-YOUR_XFYUN_APP_KEY",
    "YOUR_MAIBOT_WEBUI_PASSWORD",
    "YOUR_ONEBOT_HTTP_TOKEN",
)


def _find_violation(text: str) -> Optional[str]:
    """检查要合成的文本是否含危险特征；命中返回描述，安全返回 None。"""

    for pattern in _PATH_PATTERNS:
        matched = pattern.search(text)
        if matched:
            return "本机路径特征"
    for pattern in _CREDENTIAL_PATTERNS:
        matched = pattern.search(text)
        if matched:
            return "凭据特征"
    for secret in _KNOWN_SECRETS:
        if secret in text:
            return "已知密钥特征"
    return None


class MaimaiVoicePlugin(MaiBotPlugin):
    """麦麦语音插件：send_voice 工具 + Edge-TTS + QQ 语音消息。"""

    config_model = MaimaiVoiceConfig

    _last_voice_at: Dict[str, float] = {}
    _last_sing_at: Dict[str, float] = {}
    _tts_lock: Optional[asyncio.Lock] = None

    def _get_lock(self) -> asyncio.Lock:
        if self._tts_lock is None:
            self._tts_lock = asyncio.Lock()
        return self._tts_lock

    @Tool(
        "send_voice",
        description=(
            "用语音对当前聊天说一句话，像6岁小孩说话：奶声奶气、句子超短、"
            "用叠词。适合撒娇（抱抱/举高高）、道晚安、要糖糖、特别开心的时刻。"
            "内容口语化、最多一句话。注意：send_voice 只能像说话一样念；"
            "想唱歌请用 sing 工具（真唱，带旋律）。平时聊天用 reply 文字回复；"
            "语音是偶尔的惊喜，不是常态。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "要说的内容，像6岁小孩说的话，超短，用叠词，不要书面语",
                },
            },
            "required": ["text"],
        },
    )
    async def tool_send_voice(self, text: str = "", stream_id: str = "", **kwargs: Any) -> str:
        """send_voice 工具：文本 → Edge-TTS → QQ 语音消息。"""

        if not self.config.plugin.enabled:
            return "语音功能当前已关闭，请直接用文字回复。"

        text = str(text or "").strip()
        stream_id = str(stream_id or kwargs.get("chat_id") or "").strip()
        if not text:
            return "send_voice 需要提供 text（要说的内容）。"
        if not stream_id:
            return "当前会话缺少聊天流，无法发送语音。"

        max_chars = max(10, int(self.config.voice.max_chars or 80))
        if len(text) > max_chars:
            return f"语音内容太长了（{len(text)} 字 > {max_chars} 字上限），语音只适合一两句话，请改用 reply 文字回复。"

        cooldown = max(0, int(self.config.voice.cooldown_seconds or 0))
        now = time.monotonic()
        last = self._last_voice_at.get(stream_id, 0.0)
        left = int(cooldown - (now - last))
        if left > 0:
            return f"刚刚才发过语音哦，{left} 秒内先用文字聊吧。"

        violation = _find_violation(text)
        if violation is not None:
            logger.warning("send_voice 拒绝含%s的语音文本: %r", violation, text[:24])
            return "语音内容包含不适合说出去的信息，请换成普通聊天内容。"

        try:
            async with self._get_lock():
                audio = await asyncio.wait_for(self._synthesize(text), timeout=45.0)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Edge-TTS 合成失败: %s", exc)
            return "语音合成失败（网络问题？），这次先用文字回复吧。"

        audio_b64 = base64.b64encode(audio).decode("utf-8")
        try:
            result = await self.ctx.send.custom("voice", audio_b64, stream_id, return_details=True)
        except Exception as exc:  # noqa: BLE001
            logger.warning("语音发送失败: %s", exc)
            return "语音发送失败，这次先用文字回复吧。"

        self._last_voice_at[stream_id] = now
        sent = bool(result) if not isinstance(result, dict) else bool(result.get("sent"))
        if not sent:
            logger.warning("语音发送未确认成功: %r", result)
            return "语音发送似乎没有成功，这次先用文字回复吧。"

        logger.info("语音已发送（%d 字, %dB）", len(text), len(audio))
        return f"语音已发送：{text}"

    @Tool(
        "sing",
        description=(
            "给当前聊天真的唱一首歌（不是念歌词，是真唱，带旋律）。"
            "只在对方让你唱歌、或者你特别开心想唱歌的时候用。"
            "曲库很大（几十首），你不用背歌单：拿不准会唱什么、或对方问你会唱什么歌，"
            "就直接调用本工具并把 song 填成对方说的歌名——不在曲库里会返回完整歌单，"
            "你照着歌单回答对方就行。song 留空=随便唱一首。唱完可以配一句文字撒娇。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "song": {
                    "type": "string",
                    "description": "歌名或关键词，如「小星星」「数星星」；留空=随便唱一首",
                },
            },
            "required": [],
        },
    )
    async def tool_sing(self, song: str = "", stream_id: str = "", **kwargs: Any) -> str:
        """sing 工具：发送预先渲染好的派蒙音色儿歌（真唱）。"""

        if not self.config.plugin.enabled:
            return "语音功能当前已关闭，请直接用文字回复。"

        stream_id = str(stream_id or kwargs.get("chat_id") or "").strip()
        if not stream_id:
            return "当前会话缺少聊天流，无法唱歌。"

        songs = _load_song_index()
        if not songs:
            return "现在还不会唱任何歌（曲库是空的），先用文字回复吧。"

        cooldown = max(0, int(self.config.voice.sing_cooldown_seconds or 180))
        now = time.monotonic()
        left = int(cooldown - (now - self._last_sing_at.get(stream_id, 0.0)))
        if left > 0:
            return f"刚唱过啦，{left} 秒后再唱吧。"

        want = str(song or "").strip().lower()
        picked = None
        if want:
            for item in songs:
                keys = [str(item.get("name") or "").lower()] + [
                    str(a).lower() for a in (item.get("aliases") or [])
                ]
                if any(k and (k in want or want in k) for k in keys):
                    picked = item
                    break
            if picked is None:
                # 曲库里没有这首：把现有歌单还给规划器，让她如实告诉对方
                names = [str(s.get("name") or "") for s in songs if s.get("name")]
                preview = "、".join(names[:20])
                more = f" 等 {len(names)} 首" if len(names) > 20 else ""
                return (
                    f"曲库里没有《{song}》，不能乱唱别的歌。现在会唱：{preview}{more}。"
                    "把这份歌单告诉对方，让他挑一首。"
                )
        if picked is None:
            import random

            picked = random.choice(songs)

        path = os.path.join(SONG_DIR, str(picked.get("file") or ""))
        if not os.path.isfile(path):
            logger.warning("sing 曲库文件缺失: %s", path)
            return "这首歌的音频文件丢了，先用文字回复吧。"

        try:
            with open(path, "rb") as f:
                audio = f.read()
        except OSError as exc:
            logger.warning("sing 读取音频失败: %s", exc)
            return "唱歌的音频读不出来，先用文字回复吧。"

        audio_b64 = base64.b64encode(audio).decode("utf-8")
        try:
            result = await self.ctx.send.custom("voice", audio_b64, stream_id, return_details=True)
        except Exception as exc:  # noqa: BLE001
            logger.warning("唱歌发送失败: %s", exc)
            return "唱歌发送失败，这次先用文字回复吧。"

        sent = bool(result) if not isinstance(result, dict) else bool(result.get("sent"))
        if not sent:
            logger.warning("唱歌发送未确认成功: %r", result)
            return "歌好像没发出去，这次先用文字回复吧。"

        self._last_sing_at[stream_id] = now
        logger.info("唱歌已发送：%s（%dB）", picked.get("name"), len(audio))
        return f"唱完了：《{picked.get('name')}》。可以问问哥哥好不好听。"

    async def _synthesize(self, text: str) -> bytes:
        """按配置的引擎合成语音：rvc=本地大肥鱼音色服务，edge=原版 edge-tts。"""

        engine = str(self.config.voice.engine or "rvc").strip().lower()
        if engine == "rvc":
            return await self._synthesize_rvc(text)
        return await self._synthesize_edge(text)

    async def _synthesize_rvc(self, text: str) -> bytes:
        """调用本地 RVC 语音服务：文字 → 大肥鱼音色 wav 字节。"""

        import json
        import urllib.request

        url = str(self.config.voice.rvc_service_url or "http://127.0.0.1:9880/tts").strip()
        body = json.dumps({"text": text}, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        loop = asyncio.get_event_loop()
        try:
            response = await asyncio.wait_for(
                loop.run_in_executor(None, lambda: urllib.request.urlopen(req, timeout=60)),
                timeout=90.0,
            )
            audio = response.read()
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"RVC 服务调用失败: {exc}") from exc
        if not audio:
            raise RuntimeError("RVC 服务返回空音频")
        return audio

    async def _synthesize_edge(self, text: str) -> bytes:
        """调用 Edge-TTS 合成音频，返回 mp3 字节。"""

        import edge_tts

        communicate = edge_tts.Communicate(
            text,
            self.config.voice.voice_name,
            rate=self.config.voice.rate,
            pitch=self.config.voice.pitch,
        )
        chunks: list[bytes] = []
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                chunks.append(chunk["data"])
        audio = b"".join(chunks)
        if not audio:
            raise RuntimeError("Edge-TTS 返回空音频")
        return audio

    async def on_load(self) -> None:
        """加载时检查 edge-tts 可用性，尽早暴露环境问题。"""

        try:
            import edge_tts  # noqa: F401

            logger.info(
                "maimai-voice 已加载：声线=%s 冷却=%ds 上限=%d 字",
                self.config.voice.voice_name,
                self.config.voice.cooldown_seconds,
                self.config.voice.max_chars,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("edge-tts 不可用，send_voice 将无法工作: %s", exc)

    async def on_unload(self) -> None:
        """插件卸载钩子（要求实现）。"""

        self._last_voice_at.clear()
        self._last_sing_at.clear()

    async def on_config_update(self, new_config: Any) -> None:
        """配置热更新钩子（要求实现）。"""

        try:
            self.config = new_config
            logger.info(
                "maimai-voice 配置已更新：声线=%s 冷却=%ds 上限=%d 字",
                self.config.voice.voice_name,
                self.config.voice.cooldown_seconds,
                self.config.voice.max_chars,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("maimai-voice 配置热更新失败，沿用原配置: %s", exc)


def create_plugin() -> MaimaiVoicePlugin:
    """创建插件实例。"""
    return MaimaiVoicePlugin()
