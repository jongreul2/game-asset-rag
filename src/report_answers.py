# -*- coding: utf-8 -*-
"""results/answers_*.jsonl + results/answer_verdicts.json → results/answer_eval.md

코드로 세는 것: 모른다 처리율, 정답 인용률, 인용 유효성, 토큰·달러·지연.
LLM 판정관이 세는 것: 주장 단위 충실도(src/judge_answers.py).

사용:
    python src/report_answers.py
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import RESULTS, load_jsonl  # noqa: E402

MODELS = [("opus-5", "Opus 5"), ("sonnet-5", "Sonnet 5")]
TYPE_KO = {"attribute": "속성", "usage": "용도", "lore": "설정", "cross": "교차", "visual": "시각", "negative": "답 없음"}


def pct(a: int, b: int) -> str:
    return "%d/%d (%.0f%%)" % (a, b, 100.0 * a / b) if b else "-"


def correct(r: dict) -> bool:
    """답이 있는 질문: 답했고 정답 문서를 인용했다. 답이 없는 질문: 모른다고 했다.
    "없다"고 하면서 대안으로 정답 문서를 나열한 답은 맞은 것으로 치지 않는다."""
    if r["query_type"] == "negative":
        return r["answerable"] is False
    return r["answerable"] is True and bool(set(r["cited_ids"]) & set(r["relevant_ids"]))


def summarize(rows: list[dict], verdicts: dict, tag: str) -> dict:
    pos = [r for r in rows if r["query_type"] != "negative"]
    neg = [r for r in rows if r["query_type"] == "negative"]
    claims = [(r, c) for r in rows for c in verdicts["%s|%s" % (tag, r["qid"])]["claims"]]
    bad = [(r, c) for r, c in claims if c["verdict"] == "unsupported"]
    lat = sorted(r["latency_s"] for r in rows)
    cited_prec = [len(set(r["cited_ids"]) & set(r["relevant_ids"])) / len(r["cited_ids"]) for r in pos if r["cited_ids"]]
    return {
        "n": len(rows), "pos": pos, "neg": neg, "claims": len(claims), "bad": bad,
        "bad_answers": len({r["qid"] for r, _ in bad}),
        "retrieved_hit": sum(bool(set(r["retrieved_ids"]) & set(r["relevant_ids"])) for r in pos),
        "answered": sum(r["answerable"] is True for r in pos),
        "cited_hit": sum(correct(r) for r in pos),
        "cited_prec": statistics.mean(cited_prec),
        "abstain": sum(r["answerable"] is False for r in neg),
        "cite_outside": sum(not set(r["cited_ids"]) <= set(r["retrieved_ids"]) for r in rows),
        "not_end_turn": sum(r["stop_reason"] != "end_turn" for r in rows),
        "in_tok": statistics.mean(r["input_tokens"] for r in rows),
        "out_tok": statistics.mean(r["output_tokens"] for r in rows),
        "cost": statistics.mean(r["cost_usd"] for r in rows),
        "cost_total": sum(r["cost_usd"] for r in rows),
        "lat_med": statistics.median(lat), "lat_p90": lat[int(0.9 * (len(lat) - 1))], "lat_max": lat[-1],
    }


def main() -> None:
    verdicts = json.loads((RESULTS / "answer_verdicts.json").read_text(encoding="utf-8"))
    data = {tag: load_jsonl(RESULTS / ("answers_%s.jsonl" % tag)) for tag, _ in MODELS}
    S = {tag: summarize(data[tag], verdicts, tag) for tag, _ in MODELS}
    judge_cost = json.loads((RESULTS / "answer_judge.cost.json").read_text(encoding="utf-8"))["cost_usd_total"]
    n_pos, n_neg = len(S["opus-5"]["pos"]), len(S["opus-5"]["neg"])

    L = ["# 답변 생성 평가", "",
         "질문 %d개 = 답이 있는 질문 %d개(유형 5개 × 4개, 고정 시드) + 답이 없는 질문 %d개 · 검색 B·dense 상위 5개 · "
         "effort=low · 구조화 출력(JSON 스키마)" % (n_pos + n_neg, n_pos, n_neg), "",
         "## 주 결과", "", "| | " + " | ".join(name for _, name in MODELS) + " |", "|---|" + "---|" * len(MODELS)]

    def row(label, fn):
        L.append("| %s | %s |" % (label, " | ".join(fn(S[tag]) for tag, _ in MODELS)))

    row("**충실도** — 근거 없는 주장 / 전체 주장", lambda s: "%d / %d (%.1f%%)" % (len(s["bad"]), s["claims"], 100.0 * len(s["bad"]) / s["claims"]))
    row("근거 없는 주장이 하나라도 있는 답", lambda s: pct(s["bad_answers"], s["n"]))
    row("**답 없는 질문에 \"모른다\"**", lambda s: pct(s["abstain"], len(s["neg"])))
    row("답 있는 질문에 답함", lambda s: pct(s["answered"], len(s["pos"])))
    row("└ 답했고 정답 문서를 근거로 인용", lambda s: pct(s["cited_hit"], len(s["pos"])))
    row("(참고) 검색 상위 5개에 정답 문서 포함", lambda s: pct(s["retrieved_hit"], len(s["pos"])))
    row("인용 정밀도 — 인용한 문서 중 정답 문서 비율", lambda s: "%.2f" % s["cited_prec"])
    row("검색 결과 밖의 id 를 인용한 답", lambda s: pct(s["cite_outside"], s["n"]))
    row("중단(refusal·max_tokens)", lambda s: pct(s["not_end_turn"], s["n"]))
    row("요청당 토큰 (입력 / 출력)", lambda s: "%.0f / %.0f" % (s["in_tok"], s["out_tok"]))
    row("**요청당 비용**", lambda s: "$%.4f" % s["cost"])
    row("**지연** 중앙값 / p90 / 최대", lambda s: "%.1f초 / %.1f초 / %.1f초" % (s["lat_med"], s["lat_p90"], s["lat_max"]))

    L += ["", "> 출력 토큰에는 모델의 사고(adaptive thinking) 토큰이 포함된다. 지연은 요청을 보내고 답 전체를 받을 때까지의 시간이며 "
          "SDK 의 자동 재시도(최대 2회)가 끼면 그만큼 늘어난다. 검색 단계(질문 임베딩 1회)는 포함하지 않았다.", "",
          "> Opus 5 의 최대값 146.8초(q056 \"하늘을 날게 해주는 물약\")는 재현된다: 재시도를 끄고 다시 보내도 124.6초, "
          "JSON 스키마 강제를 빼면 같은 입력이 4.5초, 같은 스키마로 Sonnet 5 는 2.8초. 구조화 출력 경로가 이 입력에서만 멈추는 현상으로, "
          "API 안쪽의 원인은 확인할 수 없었다(2026-09-17 확인, 요청 id req_011Cf98MgZnQ5wBA3fZsYJir).", "",
          "> 이번 평가에 쓴 돈: 답변 생성 %s · 충실도 판정 $%.2f"
          % (" + ".join("%s $%.2f" % (name, S[tag]["cost_total"]) for tag, name in MODELS), judge_cost), ""]

    L += ["## 근거 없음으로 판정된 주장 (전부)", ""]
    any_bad = False
    for tag, name in MODELS:
        for r, c in S[tag]["bad"]:
            any_bad = True
            L += ["- **%s · %s** \"%s\"" % (name, r["qid"], r["query"]), "  - 주장: %s" % c["claim"], "  - 판정 이유: %s" % c["reason"]]
    if not any_bad:
        L.append("없음")

    L += ["", "## 기대와 다르게 답한 질문", "",
          "기대 = 답이 있는 질문에는 정답 문서를 인용해 답하고, 답이 없는 질문에는 모른다고 한다.", ""]
    for tag, name in MODELS:
        for r in data[tag]:
            is_neg = r["query_type"] == "negative"
            if not correct(r):
                found = "" if is_neg else (" · 검색은 정답 문서를 %s" % ("찾았다" if set(r["retrieved_ids"]) & set(r["relevant_ids"]) else "놓쳤다"))
                L += ["- **%s · %s (%s)** \"%s\" → %s%s" % (name, r["qid"], TYPE_KO[r["query_type"]], r["query"],
                                                            "답함" if r["answerable"] else "모른다", found),
                      "  > %s" % r["answer"]]

    L += ["", "## 전체 답변", ""]
    for tag, name in MODELS:
        L += ["<details><summary>%s — %d개</summary>" % (name, len(data[tag])), "",
              "| 질문 | 유형 | 판단 | 답 | 인용 |", "|---|---|---|---|---|"]
        for r in data[tag]:
            L.append("| %s | %s | %s | %s | %s |" % (r["query"], TYPE_KO[r["query_type"]], "답함" if r["answerable"] else "모른다",
                                                    r["answer"].replace("|", "/").replace("\n", " "), ", ".join(r["cited_ids"]) or "-"))
        L += ["", "</details>", ""]

    (RESULTS / "answer_eval.md").write_text("\n".join(L) + "\n", encoding="utf-8", newline="\n")
    print("\n".join(L[:22]))


if __name__ == "__main__":
    main()
