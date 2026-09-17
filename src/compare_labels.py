# -*- coding: utf-8 -*-
"""모델별 자동 라벨을 비교하고, 사람이 만든 정답(eval/label_gold.jsonl)이 있으면 정확도까지 낸다.

정답셋이 비어 있어도 돌아간다 — 그 경우 모델 간 일치도·정직도 지표만 나온다.

사용:
    python src/compare_labels.py
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import EVAL, RESULTS, items, load_jsonl  # noqa: E402

UNKNOWN = {"불명", "알 수 없음", "미상", "확인 불가"}
# object_kind 채점 임계값. 문자 바이그램 자카드가 이 값 이상이면 '일치'로 본다.
# 경계 사례(임계값 ±0.1)는 따로 뽑아 사람이 확인한다 — 자동 채점을 믿는 구간과
# 사람이 봐야 하는 구간을 나눠 두는 것이 이 점수의 전부다.
MATCH_THRESHOLD = 0.30


def bigrams(s: str) -> set[str]:
    s = "".join(s.split())
    return {s[i:i + 2] for i in range(len(s) - 1)} or {s}


def similarity(a: str, b: str) -> float:
    x, y = bigrams(a), bigrams(b)
    return len(x & y) / len(x | y) if x | y else 0.0


def jaccard(a: list[str], b: list[str]) -> float:
    x, y = set(a), set(b)
    return len(x & y) / len(x | y) if x | y else 0.0


def load_labels() -> dict[str, dict[str, dict]]:
    out = {}
    for p in sorted(RESULTS.glob("labels_*.jsonl")):
        model = p.stem.replace("labels_", "")
        out[model] = {r["item_id"]: r["label"] for r in load_jsonl(p)}
    return out


def load_gold() -> dict[str, dict]:
    path = EVAL / "label_gold.jsonl"
    if not path.exists():
        return {}
    # object_kind 가 비어 있는 행은 아직 안 채운 것 → 채점에서 제외
    return {r["item_id"]: r for r in load_jsonl(path) if r.get("object_kind", "").strip()}


def main() -> None:
    labels = load_labels()
    if len(labels) < 1:
        raise SystemExit("results/labels_*.jsonl 이 없다. 먼저 src/label_icons.py 를 돌려라.")
    gold = load_gold()
    item_name = {it["id"]: it["name"] for it in items()}
    cost = {}
    for p in RESULTS.glob("labels_*.cost.json"):
        cost[p.stem.replace("labels_", "").replace(".cost", "")] = json.loads(p.read_text(encoding="utf-8"))

    L = ["# 자동 라벨 비교", ""]
    L.append("아이콘 이미지만 보고 만든 라벨을 모델별로 비교한다. "
             "라벨링 시점에 모델은 아이템 이름·설명을 받지 않았다.")
    L.append("")

    # --- 1. 모델별 지표 ---
    L.append("## 모델별 지표")
    L.append("")
    L.append("| 모델 | 건수 | 태그 수(평균) | 재질을 '불명'으로 남김 | 비용(USD) |")
    L.append("|---|---|---|---|---|")
    for m, d in labels.items():
        tags = statistics.mean(len(v["tags"]) for v in d.values())
        unk = sum(1 for v in d.values() if v["material_guess"].strip() in UNKNOWN)
        c = cost.get(m, {}).get("cost_usd")
        L.append("| %s | %d | %.1f | %d / %d | %s |"
                 % (m, len(d), tags, unk, len(d), ("$%.3f" % c) if c else "—"))
    L.append("")
    L.append("> 아이콘이 흑백 실루엣이라 재질 정보는 이미지에 **없다**. "
             "'불명'으로 남긴 비율이 높을수록 모르는 것을 지어내지 않았다는 뜻이다.")
    L.append("")

    # --- 2. 모델 간 일치도 ---
    names = list(labels)
    if len(names) >= 2:
        a, b = names[0], names[1]
        common = sorted(set(labels[a]) & set(labels[b]))
        tag_j = statistics.mean(jaccard(labels[a][k]["tags"], labels[b][k]["tags"]) for k in common)
        kind_sim = [(k, similarity(labels[a][k]["object_kind"], labels[b][k]["object_kind"])) for k in common]
        disagree = [k for k, s in kind_sim if s == 0.0]
        L.append("## 모델 간 일치도 (%s vs %s)" % (a, b))
        L.append("")
        L.append("| 항목 | 값 |")
        L.append("|---|---|")
        L.append("| 비교 대상 | %d건 |" % len(common))
        L.append("| 태그 자카드 유사도(평균) | **%.2f** |" % tag_j)
        L.append("| 표현이 전혀 겹치지 않는 아이템 | %d건 (%.0f%%) |" % (len(disagree), 100 * len(disagree) / len(common)))
        L.append("")
        L.append("두 모델의 태그가 거의 겹치지 않는다는 것은, **어느 모델로 라벨을 만드느냐가 "
                 "검색 결과를 바꾼다**는 뜻이다. 라벨링 모델 선택은 비용만으로 결정할 문제가 아니다.")
        L.append("")
        L.append("⚠ **이 %d건을 '판독이 틀렸다'로 읽으면 안 된다.** 이 지표는 글자 겹침만 보는 "
                 "어휘 단위 측정이라, `긴 외투, 로브` vs `긴 코트/재킷` 처럼 **둘 다 맞는 동의어**도 "
                 "불일치로 잡는다. 실제로 어느 쪽이 맞았는지는 아래 정답셋 대비 정확도에서만 나온다 — "
                 "여기서는 \"두 모델이 같은 그림을 다르게 적는다\"는 사실까지만 읽는다." % len(disagree))
        L.append("")
        L.append("<details><summary>표현이 갈린 아이템 %d건</summary>" % len(disagree))
        L.append("")
        L.append("| 아이템 | %s | %s |" % (a, b))
        L.append("|---|---|---|")
        for k in disagree:
            L.append("| %s | %s | %s |" % (item_name[k], labels[a][k]["object_kind"], labels[b][k]["object_kind"]))
        L.append("")
        L.append("</details>")
        L.append("")

    # --- 3. 정답셋 대비 정확도 ---
    L.append("## 정답 라벨 대비 정확도")
    L.append("")
    if not gold:
        L.append("⏳ `eval/label_gold.jsonl` 이 아직 비어 있다. "
                 "사람이 채우면 이 절에 모델별 정확도가 채워진다.")
        L.append("")
        L.append("정답 라벨은 **사람이 만든다** — 모델 라벨을 다른 모델로 채점하면 기준선이 되지 못한다.")
    else:
        L.append("채점 기준: `object_kind` 의 문자 바이그램 자카드 ≥ %.2f 이면 일치로 본다. "
                 "임계값 근처(±0.1)는 자동 판정을 믿지 않고 아래에 따로 뽑아 사람이 확인한다." % MATCH_THRESHOLD)
        L.append("")
        L.append("| 모델 | 채점 대상 | 일치 | 정확도 | 경계 사례 |")
        L.append("|---|---|---|---|---|")
        borderline: dict[str, list] = {}
        for m, d in labels.items():
            scored = [(k, similarity(d[k]["object_kind"], gold[k]["object_kind"])) for k in gold if k in d]
            hit = sum(1 for _, s in scored if s >= MATCH_THRESHOLD)
            bl = [k for k, s in scored if abs(s - MATCH_THRESHOLD) <= 0.10]
            borderline[m] = bl
            L.append("| %s | %d | %d | **%.0f%%** | %d |"
                     % (m, len(scored), hit, 100 * hit / len(scored) if scored else 0, len(bl)))
        L.append("")
        for m, bl in borderline.items():
            if not bl:
                continue
            L.append("<details><summary>%s — 사람이 확인할 경계 사례 %d건</summary>" % (m, len(bl)))
            L.append("")
            L.append("| 아이템 | 정답(사람) | 모델 |")
            L.append("|---|---|---|")
            for k in bl:
                L.append("| %s | %s | %s |" % (item_name[k], gold[k]["object_kind"], labels[m][k]["object_kind"]))
            L.append("")
            L.append("</details>")
            L.append("")

    path = RESULTS / "label_comparison.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(L), encoding="utf-8")
    print("작성: results/label_comparison.md (%d줄)" % len(L))
    if not gold:
        print("정답 라벨이 비어 있어 정확도 절은 비워 뒀다 — eval/label_gold.jsonl 을 채우면 다시 돌려라.")


if __name__ == "__main__":
    main()
