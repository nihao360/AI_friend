# -*- coding: utf-8 -*-
"""麦麦本地语音服务：文字 → TTS → (可选)RVC → wav

两种 TTS 后端（config 里的 tts_engine）：
- gsv  : GPT-SoVITS v2Pro 零样本克隆（大肥鱼参考音色），热延迟 ~2.3s，语气自然
- edge : edge-tts 晓伊，热延迟 ~1s，机械味较重

rvc_enabled=true 时在 TTS 之后串联 RVC 转换（大肥鱼音色微调，热延迟 +1.8s）。

启动：E:\\ai-voice\\venv\\Scripts\\python.exe E:\\ai-voice\\voice-server.py
接口：POST /tts  {"text": "..."}  -> audio/wav 字节
健康：GET /health
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import uuid
from urllib.parse import quote

# RVC 的模型路径是相对 cwd 的（now_dir = os.getcwd()），必须先切到 Applio 目录
os.chdir(r"E:\ai-voice\Applio")
sys.path.insert(0, r"E:\ai-voice\Applio")
sys.stdout.reconfigure(encoding="utf-8")

import librosa  # noqa: E402
import soundfile as sf  # noqa: E402
import uvicorn  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.responses import JSONResponse, Response  # noqa: E402
from starlette.concurrency import run_in_threadpool  # noqa: E402

# ---------------- 配置 ----------------
CONFIG_PATH = r"E:\ai-voice\voice-config.json"


def _load_config() -> dict:
    defaults = {
        "tts_engine": "gsv",            # gsv | edge
        "rvc_enabled": False,           # TTS 之后再串联 RVC
        "gsv_url": "http://127.0.0.1:9881/tts",
        "gsv_ref_audio": r"E:/ai-voice/models/ref.wav",
        "gsv_prompt_text": "哥哥抱抱！麦麦今天乖乖的呀，哥哥有没有想麦麦呢？",
        "edge_voice": "zh-CN-XiaoyiNeural",
        "edge_rate": "+4%",
        "edge_pitch": "+12Hz",
        "rvc_model": r"E:/ai-voice/models/paimon/cn/paimon_cn.pth",
        "rvc_index": r"E:/ai-voice/models/paimon/cn/added_IVF522_Flat_nprobe_1_paimon_cn_v2.index",
        "rvc_pitch": 0,
        "rvc_index_rate": 0.7,
    }
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            defaults.update(json.load(f))
    except Exception:
        pass
    return defaults


CFG = _load_config()
MODELS = r"E:\ai-voice\models"
# 音色模型由 voice-config.json 的 rvc_model / rvc_index 决定
MODEL_PTH = CFG["rvc_model"]
MODEL_INDEX = CFG["rvc_index"]
TMP_DIR = r"E:\ai-voice\tmp"
os.makedirs(TMP_DIR, exist_ok=True)

APP = FastAPI()
_VC = None
_READY = {"loaded": False, "error": None}


def _get_vc():
    """懒加载 VoiceConverter；hubert 只加载一次（默认每次 convert 都重读 360MB）。"""
    global _VC
    if _VC is None:
        from rvc.infer.infer import VoiceConverter

        t0 = time.time()
        _VC = VoiceConverter()
        _orig_load_hubert = _VC.load_hubert

        def _cached_load_hubert(embedder_model, embedder_model_custom=None):
            if _VC.hubert_model is not None:
                return
            _orig_load_hubert(embedder_model, embedder_model_custom)

        _VC.load_hubert = _cached_load_hubert
        print(f"[voice-server] VoiceConverter 初始化 {time.time()-t0:.1f}s", flush=True)
    return _VC


async def _tts_gsv(text: str) -> bytes:
    """GPT-SoVITS 零样本合成（参考音色=大肥鱼），返回 wav 字节。"""
    import urllib.request

    url = (
        f"{CFG['gsv_url']}?text={quote(text)}&text_lang=zh"
        f"&ref_audio_path={quote(CFG['gsv_ref_audio'])}"
        f"&prompt_text={quote(CFG['gsv_prompt_text'])}&prompt_lang=zh"
        f"&text_split_method=cut5&media_type=wav"
    )
    loop = asyncio.get_event_loop()

    def _fetch() -> bytes:
        with urllib.request.urlopen(url, timeout=180) as resp:
            return resp.read()

    return await asyncio.wait_for(loop.run_in_executor(None, _fetch), timeout=200.0)


async def _tts_edge(text: str) -> bytes:
    """edge-tts 合成，返回 mp3 字节。"""
    import edge_tts

    communicate = edge_tts.Communicate(
        text, CFG["edge_voice"], rate=CFG["edge_rate"], pitch=CFG["edge_pitch"]
    )
    audio = b""
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio += chunk["data"]
    if not audio:
        raise RuntimeError("edge-tts 返回空音频")
    return audio


def _to_wav_bytes(raw: bytes) -> bytes:
    """任意音频字节 → wav（统一走 librosa 解码）。"""
    token = uuid.uuid4().hex[:8]
    src = os.path.join(TMP_DIR, f"src_{token}.bin")
    dst = os.path.join(TMP_DIR, f"dst_{token}.wav")
    try:
        with open(src, "wb") as f:
            f.write(raw)
        audio, sr = librosa.load(src, sr=None)
        sf.write(dst, audio, sr)
        with open(dst, "rb") as f:
            return f.read()
    finally:
        for p in (src, dst):
            try:
                os.remove(p)
            except OSError:
                pass


def _rvc_convert(wav_bytes: bytes) -> bytes:
    """wav → RVC 大肥鱼音色 → wav 字节（同步，线程池执行）。"""
    vc = _get_vc()
    token = uuid.uuid4().hex[:8]
    in_wav = os.path.join(TMP_DIR, f"rvc_in_{token}.wav")
    out_wav = os.path.join(TMP_DIR, f"rvc_out_{token}.wav")
    try:
        with open(in_wav, "wb") as f:
            f.write(wav_bytes)
        vc.convert_audio(
            audio_input_path=in_wav,
            audio_output_path=out_wav,
            model_path=MODEL_PTH,
            index_path=MODEL_INDEX,
            pitch=int(CFG["rvc_pitch"]),
            f0_method="rmvpe",
            index_rate=float(CFG["rvc_index_rate"]),
            volume_envelope=1.0,
            protect=0.33,
            hop_length=128,
            embedder_model="contentvec",
            export_format="WAV",
        )
        with open(out_wav, "rb") as f:
            return f.read()
    finally:
        for p in (in_wav, out_wav):
            try:
                os.remove(p)
            except OSError:
                pass


@APP.get("/health")
async def health():
    return {
        "ready": _READY["loaded"],
        "error": _READY["error"],
        "tts_engine": CFG["tts_engine"],
        "rvc_enabled": CFG["rvc_enabled"],
    }


@APP.post("/tts")
async def tts(payload: dict):
    text = str((payload or {}).get("text") or "").strip()
    if not text:
        return JSONResponse({"error": "text 为空"}, status_code=400)
    if len(text) > 120:
        text = text[:120]
    t0 = time.time()
    try:
        if CFG["tts_engine"] == "gsv":
            raw = await _tts_gsv(text)
            wav = _to_wav_bytes(raw) if not raw[:4] == b"RIFF" else raw
        else:
            mp3 = await _tts_edge(text)
            wav = _to_wav_bytes(mp3)
        t_tts = time.time() - t0
        if CFG["rvc_enabled"]:
            wav = await run_in_threadpool(_rvc_convert, wav)
        _READY["loaded"] = True
        _READY["error"] = None
        print(
            f"[voice-server] OK '{text[:20]}' engine={CFG['tts_engine']} rvc={CFG['rvc_enabled']} "
            f"model={os.path.basename(str(MODEL_PTH))} pitch={CFG['rvc_pitch']} "
            f"ir={CFG['rvc_index_rate']} tts={t_tts:.1f}s total={time.time()-t0:.1f}s {len(wav)}B",
            flush=True,
        )
        return Response(content=wav, media_type="audio/wav")
    except Exception as exc:  # noqa: BLE001
        _READY["error"] = str(exc)
        print(f"[voice-server] 失败: {exc}", flush=True)
        return JSONResponse({"error": str(exc)}, status_code=500)


@APP.on_event("startup")
async def warmup():
    try:
        if CFG["rvc_enabled"]:
            await run_in_threadpool(_get_vc)
        _READY["loaded"] = True
        print(
            f"[voice-server] 启动完成：tts_engine={CFG['tts_engine']} rvc={CFG['rvc_enabled']}",
            flush=True,
        )
    except Exception as exc:  # noqa: BLE001
        _READY["error"] = str(exc)
        print(f"[voice-server] 预热失败: {exc}", flush=True)


if __name__ == "__main__":
    uvicorn.run(APP, host="127.0.0.1", port=9880, log_level="warning")
