# -*- coding: utf-8 -*-
"""검색 + 답변 생성 — 평가(src/answer_eval.py)와 NPC 서버가 같이 쓰는 모듈.

검색기는 검색 평가에서 가장 좋았던 조건 B·dense(텍스트 + Sonnet 5 자동 라벨, voyage-4)다.
답변 모델은 검색된 문서 K개만 보고 답한다. 문서에 없는 내용은 "모른다"고 해야 한다.

답변 형식(JSON 스키마로 강제)
  answerable  문서 안에 질문의 답이 있는가
  answer      플레이어에게 하는 말(2~4문장)
  cited_ids   답의 근거로 쓴 문서 id — 검색된 문서 밖의 id 가 나오면 평가에서 오류로 센다

사용:
    python src/rag.py "불에 잘 버티는 방패 추천해줘"
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import PRICING, require_key  # noqa: E402
from search_eval import Embedder, build_corpora  # noqa: E402

ANSWER_MODEL = "claude-opus-5"
CORPUS = "B:sonnet-5"
K = 5

SYSTEM = """너는 게임 「에버셰이드 연대기」의 안내원 NPC 다. 플레이어의 질문에 <docs> 안의 문서만 근거로 답한다.

규칙
- 문서에 적힌 사실만 말한다. 문서에 없는 아이템·수치·장소·인물을 지어내지 않는다. 네가 아는 다른 게임 지식도 쓰지 않는다.
- 질문의 조건을 문서의 수치와 실제로 대조한다(예: "레벨 70 이상"이면 요구 레벨이 70 이상인 문서가 있어야 한다).
- 문서 안에 질문의 답이 없으면 answerable 을 false 로 하고, 모른다고 분명히 말한다. 비슷해 보이는 것을 답인 것처럼 내밀지 않는다.
  관련이 있는 대안이 문서에 있을 때만 "찾는 것은 없지만 …" 하고 한 문장으로 덧붙일 수 있다.
- 답은 한국어 2~4문장. 아이템·퀘스트 이름은 문서에 적힌 그대로 쓴다.
- cited_ids 에는 답에서 실제로 근거로 쓴 문서의 id 만 넣는다. 모른다고 답했고 대안도 들지 않았으면 비워 둔다.
- 문서의 "[아이콘에서 읽은 정보]" 부분은 아이콘 그림을 자동으로 읽은 것이라 틀릴 수 있다. 생김새를 묻는 질문에만 쓴다."""

SCHEMA = {
    "type": "object",
    "properties": {
        "answerable": {"type": "boolean", "description": "문서 안에 질문의 답이 있는가"},
        "answer": {"type": "string", "description": "플레이어에게 하는 말, 한국어 2~4문장"},
        "cited_ids": {"type": "array", "items": {"type": "string"}, "description": "근거로 쓴 문서 id"},
    },
    "required": ["answerable", "answer", "cited_ids"],
    "additionalProperties": False,
}


class Retriever:
    """문서 임베딩은 data/cache/ 에서 읽는다. 처음 보는 질문만 Voyage 를 한 번 부른다."""

    def __init__(self, corpus: str = CORPUS):
        self.ids, corp, self.icons = build_corpora()
        self.docs = corp[corpus]
        self.emb = Embedder()
        self.doc_emb = self.emb.text([self.docs[i] for i in self.ids], "document")

    def search(self, query: str, k: int = K) -> list[dict]:
        q = self.emb.text([query], "query")[0]
        scores = self.doc_emb @ q
        top = np.argsort(-scores)[:k]
        return [{"id": self.ids[j], "score": float(scores[j]), "text": self.docs[self.ids[j]],
                 "icon": self.icons.get(self.ids[j])} for j in top]


def docs_block(hits: list[dict]) -> str:
    return "<docs>\n%s\n</docs>" % "\n".join('<doc id="%s">\n%s\n</doc>' % (h["id"], h["text"]) for h in hits)


def cost_usd(model: str, usage) -> float:
    p = PRICING[model]
    return usage.input_tokens / 1e6 * p["in"] + usage.output_tokens / 1e6 * p["out"]


def generate(client, query: str, hits: list[dict], model: str = ANSWER_MODEL, effort: str = "low") -> dict:
    """검색 결과를 근거로 답을 만든다. 토큰·비용·지연을 함께 돌려준다."""
    t0 = time.perf_counter()
    msg = client.messages.create(
        model=model,
        max_tokens=8000,
        system=SYSTEM,
        messages=[{"role": "user", "content": "%s\n\n질문: %s" % (docs_block(hits), query)}],
        output_config={"effort": effort, "format": {"type": "json_schema", "schema": SCHEMA}},
    )
    latency = time.perf_counter() - t0
    out = {"model": model, "effort": effort, "stop_reason": msg.stop_reason, "latency_s": round(latency, 2),
           "input_tokens": msg.usage.input_tokens, "output_tokens": msg.usage.output_tokens,
           "cost_usd": round(cost_usd(model, msg.usage), 5), "request_id": msg._request_id}
    if msg.stop_reason != "end_turn":      # refusal · max_tokens 는 답으로 치지 않고 그대로 기록한다
        return dict(out, answerable=None, answer="", cited_ids=[])
    return dict(out, **json.loads(next(b.text for b in msg.content if b.type == "text")))


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    require_key("ANTHROPIC_API_KEY")
    import anthropic
    query = " ".join(sys.argv[1:])
    hits = Retriever().search(query)
    for h in hits:
        print("  %.3f  %s  %s" % (h["score"], h["id"], h["text"].split("\n")[0]))
    r = generate(anthropic.Anthropic(), query, hits)
    print("\n[%s] %s\n근거: %s\n%.1f초 · 입력 %d · 출력 %d 토큰 · $%.4f" % (
        "답함" if r["answerable"] else "모른다", r["answer"], ", ".join(r["cited_ids"]) or "-",
        r["latency_s"], r["input_tokens"], r["output_tokens"], r["cost_usd"]))


if __name__ == "__main__":
    main()
