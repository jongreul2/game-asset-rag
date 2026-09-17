# -*- coding: utf-8 -*-
"""답변 생성 실행 — 답이 있는 질문 20개 + 답이 없는 질문 6개.

질문 선택: 골든셋의 5개 유형에서 4개씩, 고정 시드로 뽑는다(답을 보고 고르지 않는다).
답이 없는 질문(query_type=negative) 6개는 전부 쓴다.
검색은 B·dense 상위 5개. 검색이 정답 문서를 놓친 질문도 빼지 않는다 — 그때 모델이
지어내는지 모른다고 하는지가 재려는 것이다.

결과는 results/answers_<모델>.jsonl 에 한 줄씩 쌓이고, 이미 있는 질문은 건너뛴다.

사용:
    python src/answer_eval.py --limit 3          # 먼저 3건으로 비용·지연 실측
    python src/answer_eval.py                    # 전체 26건
    python src/answer_eval.py --model claude-sonnet-5
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import EVAL, RESULTS, load_jsonl, require_key  # noqa: E402
from rag import ANSWER_MODEL, K, Retriever, generate  # noqa: E402

SEED = 20260917
PER_TYPE = 4
TYPES = ["attribute", "usage", "lore", "cross", "visual"]


def pick_questions() -> list[dict]:
    gold = load_jsonl(EVAL / "golden_queries.jsonl")
    rng = random.Random(SEED)
    picked = []
    for t in TYPES:
        pool = sorted((g for g in gold if g["query_type"] == t), key=lambda g: g["qid"])
        picked += rng.sample(pool, PER_TYPE)
    picked += [g for g in gold if g["query_type"] == "negative"]
    return sorted(picked, key=lambda g: g["qid"])


def out_path(model: str) -> Path:
    return RESULTS / ("answers_%s.jsonl" % model.replace("claude-", ""))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=ANSWER_MODEL)
    ap.add_argument("--effort", default="low")
    ap.add_argument("--limit", type=int, default=0, help="이번 실행에서 새로 부를 최대 건수(0 = 전부)")
    args = ap.parse_args()

    path = out_path(args.model)
    done = {r["qid"] for r in load_jsonl(path)} if path.exists() else set()
    todo = [g for g in pick_questions() if g["qid"] not in done]
    if args.limit:
        todo = todo[:args.limit]
    print("모델 %s · 남은 질문 %d개 (완료 %d개)" % (args.model, len(todo), len(done)))
    if not todo:
        return

    require_key("ANTHROPIC_API_KEY")
    import anthropic
    client = anthropic.Anthropic()
    retriever = Retriever()

    spent = 0.0
    with open(path, "a", encoding="utf-8", newline="\n") as f:
        for g in todo:
            hits = retriever.search(g["query"], K)
            r = generate(client, g["query"], hits, model=args.model, effort=args.effort)
            row = {"qid": g["qid"], "query": g["query"], "query_type": g["query_type"],
                   "relevant_ids": g["relevant_ids"], "retrieved_ids": [h["id"] for h in hits], **r}
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
            spent += r["cost_usd"]
            print("  %s [%s] %.1fs $%.4f  %s" % (g["qid"], "답함" if r["answerable"] else "모른다",
                                               r["latency_s"], r["cost_usd"], r["answer"][:60]))
    print("이번 실행 $%.4f · 건당 $%.4f" % (spent, spent / len(todo)))


if __name__ == "__main__":
    main()
