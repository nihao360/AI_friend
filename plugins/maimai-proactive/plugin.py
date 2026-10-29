# -*- coding: utf-8 -*-
"""maimai-proactive：麦麦主动找哥哥聊天（随机游走版）。

不设固定时段——像真人一样「时不时」冒出来：白天每隔一段随机时间醒来，
掷一次骰子决定要不要找哥哥说话。说什么完全交给规划器结合记忆和上下文
自行决定（对齐 MaiBot「自主决定」哲学），意图按当前时间从对应池子里抽。

防御：
- 安静检查：哥哥 min_quiet_minutes 内在私聊说过话 → 跳过
- 每日上限 daily_max；活跃窗口之外绝不动手
- 状态存盘（下次醒来时间、当日已触发次数），重启不重置不补发
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from maibot_sdk import Field, MaiBotPlugin, PluginConfigBase

logger = logging.getLogger("plugin.local.maimai-proactive")

_STATE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "plugins" / "local.maimai-proactive"

# (起止小时, 意图池)——按当前时间挑池子
_INTENT_POOLS: Tuple[Tuple[Tuple[int, int], Tuple[str, ...]], ...] = (
    ((7, 11), (
        "早上想跟哥哥打招呼，问哥哥吃什么早饭",
        "想跟哥哥说早安，撒个娇让他今天开心",
        "刚睡醒，想跟哥哥说话",
    )),
    ((11, 14), (
        "中午想问问哥哥吃饭了没",
        "想跟哥哥说自己在吃什么，问哥哥吃了什么",
        "吃完饭困困的，想找哥哥说说话",
    )),
    ((14, 18), (
        "下午想找哥哥玩，问哥哥在干嘛",
        "想给哥哥看个好玩的东西，随口分享点小事",
        "想吃零食了，跟哥哥撒娇要糖糖",
    )),
    ((18, 21), (
        "晚上想找哥哥聊天，问哥哥今天过得怎么样",
        "想跟哥哥撒娇求陪玩",
        "有点想哥哥了，想找他说说话",
    )),
    ((21, 24), (
        "睡前想跟哥哥说晚安",
        "想跟哥哥撒娇说舍不得睡",
        "困困的，想听哥哥说晚安",
    )),
)


class PluginSection(PluginConfigBase):
    """插件节。"""

    enabled: bool = Field(default=True, description="插件开关")
    config_version: str = Field(default="1.0.0", description="配置版本")


class ProactiveSection(PluginConfigBase):
    """主动聊天节。"""

    target_user_id: str = Field(default="YOUR_MASTER_QQ", description="要主动找的人（哥哥）的 QQ 号")
    daily_max: int = Field(default=4, description="每日主动触发上限")
    min_quiet_minutes: int = Field(default=50, description="目标这段时间内说过话就不打扰")
    check_interval_min_minutes: int = Field(default=35, description="两次醒来之间的最短间隔（分钟）")
    check_interval_max_minutes: int = Field(default=75, description="两次醒来之间的最长间隔（分钟）")
    per_check_probability: float = Field(default=0.3, description="每次醒来想说话的概率")
    active_from_hour: int = Field(default=7, description="活跃窗口起始小时")
    active_to_hour: int = Field(default=23, description="活跃窗口结束小时")


class MaimaiProactiveConfig(PluginConfigBase):
    """插件配置总模型。"""

    plugin: PluginSection = Field(default_factory=PluginSection)
    proactive: ProactiveSection = Field(default_factory=ProactiveSection)


class MaimaiProactivePlugin(MaiBotPlugin):
    """麦麦主动聊天插件：随机游走调度，内容交给规划器。"""

    config_model = MaimaiProactiveConfig

    _sched_task: Optional[asyncio.Task] = None
    _stop_event: Optional[asyncio.Event] = None

    # ------------------------------------------------------- 状态存取

    def _load_state(self) -> Dict[str, Any]:
        try:
            raw = (_STATE_DIR / "state.json").read_text(encoding="utf-8")
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except Exception:  # noqa: BLE001
            return {}

    def _save_state(self, state: Dict[str, Any]) -> None:
        try:
            _STATE_DIR.mkdir(parents=True, exist_ok=True)
            (_STATE_DIR / "state.json").write_text(
                json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("状态保存失败（不影响运行）: %s", exc)

    def _fresh_state(self) -> Dict[str, Any]:
        today = datetime.now().strftime("%Y-%m-%d")
        return {"date": today, "triggered_count": 0, "next_check_ts": 0.0}

    def _get_state(self) -> Dict[str, Any]:
        """取当天状态，过期则重置。"""

        state = self._load_state()
        if state.get("date") != datetime.now().strftime("%Y-%m-%d"):
            state = self._fresh_state()
            self._save_state(state)
        return state

    # ------------------------------------------------------- 调度循环

    def _next_check_seconds(self) -> float:
        """距下次醒来还有多少秒（首次/重启后给个短暖机间隔）。"""

        state = self._get_state()
        now_ts = time.time()
        next_ts = float(state.get("next_check_ts") or 0.0)
        if next_ts <= 0:
            # 首次（或重启后）：5~20 分钟内醒来一次，避免开机就打扰
            return random.uniform(5 * 60, 20 * 60)
        return max(30.0, next_ts - now_ts)

    def _schedule_next(self, state: Dict[str, Any]) -> None:
        """排下一次醒来时间并存盘。"""

        lo = max(5, int(self.config.proactive.check_interval_min_minutes or 35))
        hi = max(lo, int(self.config.proactive.check_interval_max_minutes or 75))
        wait_min = random.uniform(lo, hi)
        state["next_check_ts"] = time.time() + wait_min * 60
        self._save_state(state)
        logger.debug("下次主动检查：%.0f 分钟后", wait_min)

    def _pick_intent(self) -> str:
        """按当前时间挑一个主动意图。"""

        hour = datetime.now().hour
        for (start, end), pool in _INTENT_POOLS:
            if start <= hour < end:
                return random.choice(pool)
        return random.choice(_INTENT_POOLS[-1][1])

    async def _scheduler_loop(self) -> None:
        """主循环：睡到下次醒来，掷骰子决定要不要找哥哥说话。"""

        stop = self._stop_event
        assert stop is not None
        logger.info(
            "maimai-proactive 随机游走调度启动：目标=%s 每日上限=%d 概率=%.2f 间隔=%d-%d分钟",
            self.config.proactive.target_user_id,
            self.config.proactive.daily_max,
            self.config.proactive.per_check_probability,
            self.config.proactive.check_interval_min_minutes,
            self.config.proactive.check_interval_max_minutes,
        )
        while not stop.is_set():
            try:
                wait = self._next_check_seconds()
                if wait <= 0:
                    wait = 60.0
                try:
                    await asyncio.wait_for(stop.wait(), timeout=min(wait, 900.0))
                except asyncio.TimeoutError:
                    pass
                if stop.is_set():
                    break
                await self._maybe_reach_out()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.warning("调度循环异常（60秒后继续）: %s", exc)
                try:
                    await asyncio.wait_for(stop.wait(), timeout=60.0)
                except asyncio.TimeoutError:
                    pass

    async def _maybe_reach_out(self) -> None:
        """醒来的一次检查：到点才掷骰子，中了就触发主动聊天。"""

        state = self._get_state()
        now = datetime.now()
        now_ts = time.time()
        next_ts = float(state.get("next_check_ts") or 0.0)
        if next_ts > now_ts:
            return

        # 排下一次醒来时间（无论这次中不中）
        self._schedule_next(state)

        # 活跃窗口检查
        from_hour = max(0, int(self.config.proactive.active_from_hour or 7))
        to_hour = max(from_hour + 1, int(self.config.proactive.active_to_hour or 23))
        if not (from_hour <= now.hour < to_hour):
            logger.debug("活跃窗口外（%s），跳过", now.strftime("%H:%M"))
            return
        # 夜间保护：23:20 之后绝不再触发
        if now.hour >= 23 and now.minute >= 20:
            logger.debug("夜间保护（%s），跳过", now.strftime("%H:%M"))
            return

        # 每日上限
        triggered_count = int(state.get("triggered_count") or 0)
        daily_max = max(1, int(self.config.proactive.daily_max or 4))
        if triggered_count >= daily_max:
            logger.debug("今日主动已达上限 %d，跳过", triggered_count)
            return

        # 掷骰子
        prob = max(0.0, min(1.0, float(self.config.proactive.per_check_probability or 0.3)))
        if random.random() >= prob:
            logger.debug("这次没想说话（概率 %.2f 未中）", prob)
            return

        state["triggered_count"] = triggered_count + 1
        self._save_state(state)
        intent = self._pick_intent()
        try:
            await self._trigger_proactive(intent)
        except Exception as exc:  # noqa: BLE001
            logger.warning("主动触发失败: %s", exc)

    # ------------------------------------------------------- 触发

    async def _trigger_proactive(self, intent: str) -> None:
        """解析私聊流 → 安静检查 → 触发内置主动管线。"""

        target_id = str(self.config.proactive.target_user_id or "").strip()
        if not target_id:
            logger.warning("target_user_id 为空，跳过")
            return

        result = await self.ctx.chat.get_stream_by_user_id(user_id=target_id)
        stream = result if isinstance(result, dict) else None
        stream_id = str((stream or {}).get("stream_id") or (stream or {}).get("chat_id") or "")
        if not stream_id:
            logger.warning("找不到 %s 的私聊流", target_id)
            return

        # 安静检查：min_quiet_minutes 内哥哥发过消息就不打扰
        quiet_min = max(0, int(self.config.proactive.min_quiet_minutes or 0))
        end_ts = time.time()
        start_ts = end_ts - quiet_min * 60
        try:
            msgs = await self.ctx.message.get_by_time_in_chat(
                stream_id, str(int(start_ts)), str(int(end_ts)),
                filter_mai=False, filter_command=False,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("安静检查查询失败（视为安静继续）: %s", exc)
            msgs = []
        if isinstance(msgs, dict):
            msgs = msgs.get("messages") or []
        for msg in msgs if isinstance(msgs, list) else []:
            info = msg.get("message_info") or {}
            user = info.get("user_info") or {} if isinstance(info, dict) else {}
            if str(user.get("user_id", "") or "") == target_id:
                logger.info("哥哥 %d 分钟内在私聊说过话，这次先不打扰", quiet_min)
                return

        trigger = await self.ctx.maisaka.proactive.trigger(
            stream_id,
            intent,
            reason="maimai-proactive 随机主动",
        )
        ok = bool(trigger.get("success")) if isinstance(trigger, dict) else bool(trigger)
        if ok:
            logger.info("已触发主动聊天：%s", intent)
        else:
            logger.warning("主动触发未成功: %r", trigger)

    # ------------------------------------------------------- 生命周期

    async def on_load(self) -> None:
        if not self.config.plugin.enabled:
            logger.info("maimai-proactive 已禁用")
            return
        self._get_state()
        self._stop_event = asyncio.Event()
        self._sched_task = asyncio.create_task(self._scheduler_loop())

    async def on_unload(self) -> None:
        if self._sched_task is not None:
            self._sched_task.cancel()
            self._sched_task = None
        if self._stop_event is not None:
            self._stop_event.set()

    async def on_config_update(self, new_config: Any) -> None:
        try:
            self.config = new_config
        except Exception as exc:  # noqa: BLE001
            logger.warning("配置热更新失败，沿用原配置: %s", exc)
        if self.config.plugin.enabled and (self._sched_task is None or self._sched_task.done()):
            self._stop_event = asyncio.Event()
            self._sched_task = asyncio.create_task(self._scheduler_loop())
        elif not self.config.plugin.enabled and self._sched_task is not None:
            await self.on_unload()


def create_plugin() -> MaimaiProactivePlugin:
    """创建插件实例。"""
    return MaimaiProactivePlugin()
