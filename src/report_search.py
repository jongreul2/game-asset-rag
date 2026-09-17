# -*- coding: utf-8 -*-
"""results/search_eval.json → results/search_eval.md (표와 질문별 승패).

사용:
    python src/report_search.py
"""
from __future__ import annotations

import json
import sys
from math import comb
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import EVAL, RESULTS, load_jsonl  # noqa: E402

TYPES = [("attribute", "속성"), ("usage", "용도"), ("lore", "설정"), ("cross", "교차"), ("visual", "시각")]
MAIN = [
    ("A · dense", "**A** 텍스트만"),
    ("B:sonnet-5 · dense", "**B** 텍스트 + 자동 라벨 (Sonnet 5)"),
    ("B:haiku-4-5 · dense", "**B′** 텍스트 + 자동 라벨 (Haiku 4.5)"),
    ("B:sonnet-5 · hybrid", "**C** B + 키워드 결합(hybrid)"),
    ("D · dense", "**D** 텍스트 + 아이콘 이미지 (멀티모달)"),
    ("D0(이미지 없음) · dense", "D0 — D 와 같은 모델, 이미지 없이(대조군)"),
]
PAIRS = [
    ("A · dense", "B:sonnet-5 · dense", "A → B (Sonnet 5 라벨 추가)"),
    ("A · dense", "B:haiku-4-5 · dense", "A → B′ (Haiku 4.5 라벨 추가)"),
    ("D0(이미지 없음) · dense", "D · dense", "D0 → D (같은 모델에 이미지만 추가)"),
    ("B:sonnet-5 · dense", "B:sonnet-5 · hybrid", "B → C (키워드 검색 결합)"),
]


def sign_test(up: int, down: int) -> float:
    """양측 부호 검정 p값(동률 제외)."""
    n, k = up + down, min(up, down)
    if n == 0:
        return 1.0
    return min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) / 2 ** n)


def main() -> None:
    J = json.loads((RESULTS / "search_eval.json").read_text(encoding="utf-8"))
    R, k = J["runs"], J["k"]
    gold = {g["qid"]: g for g in load_jsonl(EVAL / "golden_queries.jsonl")}
    rk = "recall@%d" % k
    n = R["A · dense"]["all"]["n"]

    L = ["# 검색 평가", "",
         "문서 190개(아이템 150 + 퀘스트 40) · 질문 %d개 · 임베딩 `%s` / `%s`" % (n, J["text_model"], J["mm_model"]), "",
         "## 주 결과", "", "| 조건 | %s | MRR | hit@1 |" % rk, "|---|---|---|---|"]
    for key, name in MAIN:
        a = R[key]["all"]
        L.append("| %s | %.3f | %.3f | %.3f |" % (name, a[rk], a["mrr"], a["hit@1"]))

    L += ["", "## 질문 유형별 %s" % rk, "",
          "| 조건 | " + " | ".join("%s (%d)" % (ko, R["A · dense"][t]["n"]) for t, ko in TYPES) + " |",
          "|---|" + "---|" * len(TYPES)]
    for key, name in MAIN:
        L.append("| %s | " % name + " | ".join("%.3f" % R[key][t][rk] for t, _ in TYPES) + " |")
    L += ["", "> **시각** 질문은 그 단어가 아이템 텍스트에 없다는 것을 코드로 검증한 질문군이다"
              "(`src/build_golden.py`). 이미지 정보가 유리할 수밖에 없으므로 전체 평균만 보면 효과가 과장된다. "
              "그래서 유형별로 나눠 싣는다.", ""]

    L += ["## 질문별 승패 (첫 정답의 순위 기준)", "",
          "| 비교 | 좋아짐 | 나빠짐 | 같음 | 부호 검정 p(양측) |", "|---|---|---|---|---|"]
    detail = []
    for a, b, label in PAIRS:
        A = {p["qid"]: p for p in R[a]["per_query"]}
        B = {p["qid"]: p for p in R[b]["per_query"]}
        up = [q for q in A if B[q]["first_rank"] < A[q]["first_rank"]]
        dn = [q for q in A if B[q]["first_rank"] > A[q]["first_rank"]]
        L.append("| %s | %d | %d | %d | %.3f |" % (label, len(up), len(dn), len(A) - len(up) - len(dn), sign_test(len(up), len(dn))))
        detail.append((label, [(q, A[q], B[q]) for q in up + dn]))
    L.append("")
    for label, rows in detail:
        L += ["<details><summary>%s — 순위가 바뀐 질문 %d개</summary>" % (label, len(rows)), "",
              "| 유형 | 질문 | 전 | 후 |", "|---|---|---|---|"]
        for q, a, b in rows:
            L.append("| %s | %s | %d위 | %d위 |" % (dict(TYPES)[a["type"]], gold[q]["query"], a["first_rank"], b["first_rank"]))
        L += ["", "</details>", ""]

    L += ["## 전체 조합", "", "| 문서 · 검색기 | %s | MRR | hit@1 |" % rk, "|---|---|---|---|"]
    for key, r in R.items():
        L.append("| %s | %.3f | %.3f | %.3f |" % (key, r["all"][rk], r["all"]["mrr"], r["all"]["hit@1"]))
    L.append("")

    (RESULTS / "search_eval.md").write_text("\n".join(L), encoding="utf-8")
    print("작성: results/search_eval.md (%d줄)" % len(L))


if __name__ == "__main__":
    main()
