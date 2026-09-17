# -*- coding: utf-8 -*-
"""NPC 용 로컬 서버 — Unity 클라이언트는 이 서버에만 말을 건다.

API 키(Anthropic·Voyage)는 이 프로세스의 환경(.env)에만 있다. 클라이언트에는 키를 넣지 않는다 —
게임 클라이언트는 사용자 기기에서 실행되므로 넣는 순간 추출된다.

  POST /ask          {"query": "불에 잘 버티는 방패"}
                     → {"answerable", "answer", "citations": [{"id","kind","name","icon"}], "latency_s", ...}
  GET  /icons/<file> 근거 아이템 아이콘 PNG (data/icons 에 실제로 있는 파일명만 허용)
  GET  /health

127.0.0.1 에만 바인딩한다. 같은 질문의 답은 data/cache/answers.json 에 남겨 다시 물으면 API 를 부르지 않는다
(데모 영상을 여러 번 찍어도 비용이 들지 않게).

사용:
    python src/server.py                       # http://127.0.0.1:8765
    ANSWER_MODEL=claude-sonnet-5 python src/server.py
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DATA, items, quests, require_key  # noqa: E402
from rag import ANSWER_MODEL, K, Retriever, generate  # noqa: E402

HOST, PORT = "127.0.0.1", int(os.environ.get("PORT", "8765"))
MAX_QUERY = 200
ANSWER_CACHE = DATA / "cache" / "answers.json"


class Npc:
    def __init__(self):
        require_key("ANTHROPIC_API_KEY")
        # 대화는 질문 간격이 짧다. 검색 평가용 선제 대기(21초)를 끄고, 한도에 걸리면 Embedder 가 재시도한다.
        os.environ.setdefault("VOYAGE_MIN_INTERVAL", "0")
        import anthropic
        self.client = anthropic.Anthropic()
        self.model = os.environ.get("ANSWER_MODEL", ANSWER_MODEL)
        self.retriever = Retriever()
        self.meta = {it["id"]: {"kind": "item", "name": it["name"], "icon": it["icon"]} for it in items()}
        self.meta.update({q["id"]: {"kind": "quest", "name": q["title"], "icon": None} for q in quests()})
        self.icons = {it["icon"] for it in items()}
        self.lock = threading.Lock()          # 임베딩 캐시 파일을 동시에 쓰지 않게 요청을 한 줄로 세운다
        self.cache = json.loads(ANSWER_CACHE.read_text(encoding="utf-8")) if ANSWER_CACHE.exists() else {}

    def ask(self, query: str) -> dict:
        key = "%s|%s" % (self.model, query)
        with self.lock:
            if key in self.cache:
                return dict(self.cache[key], cached=True)
            t0 = time.perf_counter()
            hits = self.retriever.search(query, K)
            t_search = time.perf_counter() - t0
            r = generate(self.client, query, hits, model=self.model)
            allowed = {h["id"] for h in hits}
            out = {
                "answerable": r["answerable"], "answer": r["answer"],
                "citations": [dict(id=i, **self.meta[i]) for i in r["cited_ids"] if i in allowed],
                "model": r["model"], "search_s": round(t_search, 2), "latency_s": r["latency_s"],
                "cost_usd": r["cost_usd"], "stop_reason": r["stop_reason"],
            }
            if r["stop_reason"] == "end_turn":
                self.cache[key] = out
                ANSWER_CACHE.write_text(json.dumps(self.cache, ensure_ascii=False, indent=1), encoding="utf-8")
            return dict(out, cached=False)


class Handler(BaseHTTPRequestHandler):
    npc: Npc

    def _json(self, code: int, obj: dict) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        if self.path == "/health":
            return self._json(200, {"ok": True, "model": self.npc.model})
        if self.path.startswith("/icons/"):
            name = self.path[len("/icons/"):]
            if name not in self.npc.icons:            # 허용 목록 대조 — 경로 조작 차단
                return self._json(404, {"error": "unknown icon"})
            body = (DATA / "icons" / name).read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            return self.wfile.write(body)
        self._json(404, {"error": "not found"})

    def do_POST(self):  # noqa: N802
        if self.path != "/ask":
            return self._json(404, {"error": "not found"})
        try:
            n = int(self.headers.get("Content-Length", "0"))
            query = str(json.loads(self.rfile.read(min(n, 4096)).decode("utf-8")).get("query", "")).strip()
        except (ValueError, AttributeError):
            return self._json(400, {"error": "bad json"})
        if not query or len(query) > MAX_QUERY:
            return self._json(400, {"error": "query 는 1~%d자" % MAX_QUERY})
        try:
            self._json(200, self.npc.ask(query))
        except Exception as e:  # noqa: BLE001 — 클라이언트에는 종류만, 자세한 내용은 서버 콘솔에
            print("ask 실패:", repr(e))
            self._json(502, {"error": type(e).__name__})

    def log_message(self, fmt, *args):
        print("%s %s" % (self.address_string(), fmt % args))


def main() -> None:
    Handler.npc = Npc()
    print("NPC 서버 http://%s:%d · 답변 모델 %s" % (HOST, PORT, Handler.npc.model))
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
