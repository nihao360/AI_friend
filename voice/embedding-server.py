# -*- coding: utf-8 -*-
"""本地文本嵌入服务（OpenAI 兼容 /v1/embeddings）

模型：BAAI/bge-small-zh-v1.5（中文优化，512 维，CPU 上毫秒级）
供 MaiBot 的 embedding 任务使用，补上 A_Memorix 记忆语义检索能力。

启动：E:\\ai-voice\\emb-venv\\Scripts\\python.exe E:\\ai-voice\\embedding-server.py
接口：POST /v1/embeddings  {"input": "文本" 或 ["文本1","文本2"], "model": "bge-small-zh"}
      GET  /v1/models
      GET  /health
"""
from __future__ import annotations

import sys
import time

sys.stdout.reconfigure(encoding="utf-8")

# 本机走代理时 certifi 不认代理 CA，接系统证书库（否则 HF 下载 SSL 验证失败）
import truststore  # noqa: E402

truststore.inject_into_ssl()

import uvicorn  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastembed import TextEmbedding  # noqa: E402

MODEL_NAME = "BAAI/bge-small-zh-v1.5"
PUBLIC_MODEL_ID = "bge-small-zh"

print(f"[embedding-server] 加载模型 {MODEL_NAME} ...", flush=True)
t0 = time.time()
MODEL = TextEmbedding(model_name=MODEL_NAME, cache_dir=r"E:\ai-voice\emb-cache")
DIM = len(list(MODEL.embed(["测试"]))[0])
print(f"[embedding-server] 模型就绪 {time.time()-t0:.1f}s dim={DIM}", flush=True)

APP = FastAPI()
APP.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@APP.get("/health")
async def health():
    return {"ready": True, "model": MODEL_NAME, "dim": DIM}


@APP.get("/v1/models")
async def list_models():
    return {
        "object": "list",
        "data": [
            {
                "id": PUBLIC_MODEL_ID,
                "object": "model",
                "created": 1700000000,
                "owned_by": "local",
            }
        ],
    }


@APP.post("/v1/embeddings")
async def embeddings(payload: dict):
    raw_input = (payload or {}).get("input")
    if isinstance(raw_input, str):
        texts = [raw_input]
    elif isinstance(raw_input, list):
        texts = [str(t) for t in raw_input]
    else:
        return {"error": {"message": "input 必须是字符串或字符串数组"}}
    if not texts:
        return {"error": {"message": "input 为空"}}

    t0 = time.time()
    vectors = [v.tolist() for v in MODEL.embed(texts)]
    data = [
        {"object": "embedding", "index": i, "embedding": vec}
        for i, vec in enumerate(vectors)
    ]
    print(
        f"[embedding-server] {len(texts)} 条 -> {len(vectors[0])} 维 用时 {(time.time()-t0)*1000:.0f}ms",
        flush=True,
    )
    return {
        "object": "list",
        "data": data,
        "model": PUBLIC_MODEL_ID,
        "usage": {"prompt_tokens": sum(len(t) for t in texts), "total_tokens": sum(len(t) for t in texts)},
    }


if __name__ == "__main__":
    uvicorn.run(APP, host="127.0.0.1", port=9890, log_level="warning")
