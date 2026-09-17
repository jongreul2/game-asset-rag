# -*- coding: utf-8 -*-
"""자동 라벨 비교 리포트(results/label_comparison.md)를 만든다.

채점 설계 (2026-09-17 확정):
  정답     = 아이콘 **원작자가 붙인 이름** (data/icon_map.csv). 모델도 저자도 아닌 제3자의 기준.
  사람     = 저자가 아이콘만 보고 적은 답 → 정답이 아니라 **사람 기준선**으로 같이 채점한다.
  판정     = '같은 물건인가'를 LLM 판정관이 3단계(match/partial/miss)로 판정 (src/judge_labels.py)
  판정 검증 = 사람이 층화 표본을 블라인드로 따로 채점 → 판정관-사람 일치율 (src/make_judge_check_tool.py)

여기까지 오며 버린 설계 두 가지(같은 실수를 막으려고 남긴다):
  ✗ 문자 바이그램 자카드 채점 — 정답이 '검'처럼 짧으면 모델이 더 자세히 맞혀도 0점.
    Sonnet 25% / Haiku 21% 라는 엉터리 수치가 나와 폐기.
  ✗ 저자가 적은 답을 정답으로 쓰는 설계 — 저자도 틀릴 수 있다. 원작자 이름이라는 독립된
    기준이 이미 있었고, 그걸 정답으로 두면 저자의 답은 '사람 기준선'이 되어 모델 수치를
    해석할 수 있게 된다.

사용:
    python src/compare_labels.py
"""
from __future__ import annotations

import collections
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import EVAL, RESULTS, load_jsonl  # noqa: E402
from judge_labels import answer_key, load_verdicts, pair_key, sources  # noqa: E402

UNKNOWN_MATERIAL = {"불명", "알 수 없음", "미상", "확인 불가"}
LABEL = {"human": "사람(저자)", "sonnet-5": "Sonnet 5", "haiku-4-5": "Haiku 4.5"}


def is_unknown(answer: str) -> bool:
    """사람이 판독을 포기한 답."""
    g = answer.strip()
    return "모르" in g or g in {"?", "??", "ㅁ", "ㅁㄹ", "x", "X"}


def jaccard(a: list[str], b: list[str]) -> float:
    x, y = set(a), set(b)
    return len(x & y) / len(x | y) if x | y else 0.0


def main() -> None:
    key, verdicts, src = answer_key(), load_verdicts(), sources()
    models = [m for m in src if m != "human"]
    if not models:
        raise SystemExit("results/labels_*.jsonl 이 없다. 먼저 src/label_icons.py 를 돌려라.")
    raw = {p.stem.replace("labels_", ""): {r["item_id"]: r["label"] for r in load_jsonl(p)}
           for p in sorted(RESULTS.glob("labels_*.jsonl"))}
    cost = {p.stem.replace("labels_", "").replace(".cost", ""): json.loads(p.read_text(encoding="utf-8"))
            for p in RESULTS.glob("labels_*.cost.json")}

    L = ["# 자동 라벨 비교", "",
         "아이콘 이미지만 보고 만든 라벨을 비교한다. 라벨링 시점에 모델은 아이템 이름·설명을 받지 않았다.", ""]

    # --- 1. 정확도 ---
    human = src.get("human", {})
    common = sorted(human)
    L += ["## 정확도 — 정답은 아이콘 원작자가 붙인 이름", "",
          "정답은 [game-icons.net](https://game-icons.net) 원작자가 각 아이콘에 붙인 이름이다"
          "(예: `broadsword`, `turtle-shell`). 모델도 저자도 아닌 제3자의 기준이다.",
          "저자가 같은 아이콘을 **이름·설명 없이** 보고 적은 답을 **사람 기준선**으로 같이 채점했다 — "
          "모델 수치만 있으면 그게 높은지 낮은지 알 수 없기 때문이다.", ""]
    missing = [pair_key(key[k], a[k]) for a in src.values() for k in a if pair_key(key[k], a[k]) not in verdicts]
    if missing:
        L += ["⏳ 판정되지 않은 쌍 %d개 — `python src/judge_labels.py` 를 먼저 돌린다." % len(missing), ""]
    else:
        def tally(answers: dict[str, str], ids: list[str]) -> collections.Counter:
            return collections.Counter(verdicts[pair_key(key[k], answers[k])]["verdict"] for k in ids)

        L += ["### 같은 아이콘 %d건 기준 (사람과 모델을 같은 조건에서 비교)" % len(common), "",
              "| | 정확히 같은 물건 | 범주까지 인정 | 다른 물건 |", "|---|---|---|---|"]
        for name in ["human"] + models:
            c, n = tally(src[name], common), len(common)
            L.append("| %s | **%.1f%%** | %.1f%% | %.1f%% |"
                     % (LABEL.get(name, name), 100 * c["match"] / n, 100 * (c["match"] + c["partial"]) / n, 100 * c["miss"] / n))
        gave_up = sum(1 for k in common if is_unknown(human[k]))
        L += ["", "- 사람이 판독을 포기한 아이콘(`모르겠음`)은 %d건이며 '다른 물건'에 포함돼 있다." % gave_up,
              "- 150건 중 %d건은 사람 채점에서 뺐다. 데이터셋 개정 과정에서 저자가 아이템 이름과 아이콘을 "
              "함께 봐 버려 블라인드가 깨졌기 때문이다." % (len(key) - len(common)), ""]
        L += ["### 전체 %d건 기준 (모델만)" % len(key), "", "| | 정확히 같은 물건 | 범주까지 인정 | 다른 물건 |", "|---|---|---|---|"]
        for name in models:
            c, n = tally(src[name], sorted(src[name])), len(src[name])
            L.append("| %s | **%.1f%%** | %.1f%% | %.1f%% |"
                     % (LABEL.get(name, name), 100 * c["match"] / n, 100 * (c["match"] + c["partial"]) / n, 100 * c["miss"] / n))
        L.append("")

    # --- 2. 판정관 검증 ---
    L += ["## 판정관은 믿을 만한가", "",
          "정답은 영문 이름, 답은 한국어라 글자 비교가 안 된다. '같은 물건인가'는 LLM 판정관(Opus 5)이 "
          "3단계로 판정했다. 판정관은 답의 출처(사람/어느 모델)를 모르고, 같은 (정답, 답) 쌍은 한 번만 판정한다.", ""]
    check_path = EVAL / "judge_check.json"
    if not check_path.exists():
        L += ["⏳ 사람 검증 전 — `python src/make_judge_check_tool.py` → `tools/judge_check.html` "
              "에서 층화 표본 30건을 블라인드로 채점하면 일치율이 여기에 채워진다.", ""]
    else:
        check = json.loads(check_path.read_text(encoding="utf-8"))
        rows = [(verdicts[k]["verdict"], v) for k, v in check.items() if k in verdicts]
        agree = sum(1 for j, h in rows if j == h)
        lenient = sum(1 for j, h in rows if (j == "miss") == (h == "miss"))
        L += ["저자가 판정별로 층화한 표본 **%d건**을 판정관의 판정을 보지 않고 따로 채점했다." % len(rows), "",
              "| | 값 |", "|---|---|",
              "| 3단계 완전 일치 | **%d / %d (%.0f%%)** |" % (agree, len(rows), 100 * agree / len(rows)),
              "| 맞음(match·partial) vs 틀림(miss) 2단계 일치 | %d / %d (%.0f%%) |" % (lenient, len(rows), 100 * lenient / len(rows)), ""]
        conf = collections.Counter(rows)
        L += ["| 판정관 ↓ / 사람 → | match | partial | miss |", "|---|---|---|---|"]
        for j in ("match", "partial", "miss"):
            L.append("| %s | %d | %d | %d |" % (j, conf[(j, "match")], conf[(j, "partial")], conf[(j, "miss")]))
        # 불일치가 어디서 나는가: 답의 출처별로 나눠 본다(채점자는 출처를 몰랐다).
        owner: dict[str, set] = collections.defaultdict(set)
        for name, answers in src.items():
            for k, a in answers.items():
                owner[pair_key(key[k], a)].add(name)
        dis = [k for k, v in check.items() if k in verdicts and verdicts[k]["verdict"] != v]
        own = [k for k in dis if "human" in owner[k]]
        looser = [k for k in own if verdicts[k]["verdict"] == "partial" and check[k] == "match"]
        L += ["", "**읽는 법.** '맞았나 틀렸나'(2단계)는 판정관과 사람이 %.0f%% 일치한다. 어긋나는 곳은 거의 "
                  "'정확히 같은 물건'과 '범주만 같음'의 경계다. 따라서 위 정확도 표에서 **'범주까지 인정' 열이 더 "
                  "단단한 수치**이고, '정확히 같은 물건' 열은 이 경계의 불확실성을 안고 있다. 어느 열로 보든 "
                  "Sonnet 5 ≥ 사람 > Haiku 4.5 순서는 같다." % (100 * lenient / len(rows)), "",
              "불일치 %d건 중 **%d건은 채점자(저자) 본인이 쓴 답**이었고, 그중 %d건은 판정관이 '범주만 같음'으로 본 것을 "
              "저자가 '맞다'로 올려 준 경우다(예: `bone-knife` 에 `무기`). 출처를 가렸는데도 자기 답에 너그러웠다 — "
              "사람 채점에도 편향이 있고, 그래서 정답을 저자의 답이 아니라 원작자 이름에 둔 것이다."
              % (len(dis), len(own), len(looser)), ""]
        L += ["> 표본은 판정별 층화(match 12 · partial 9 · miss 9)다. 무작위로 뽑으면 대부분 match 라 "
                  "partial·miss 구간에서 판정관이 맞는지 볼 수 없다. 그래서 이 일치율은 전체 평균이 아니라 "
                  "'어려운 구간을 일부러 많이 본' 수치다.", ""]
    L += ["한계: 판정관과 채점 대상이 같은 계열(Claude)이다. 출처를 가렸고 과제가 사실 판단이라 "
          "자기선호 편향의 여지는 작지만 0은 아니다.", ""]

    # --- 3. 부가 지표 ---
    L += ["## 부가 지표", "", "| 모델 | 태그 수(평균) | 재질을 '불명'으로 남김 | 라벨링 비용(USD) |", "|---|---|---|---|"]
    for m in models:
        d = raw[m]
        unk = sum(1 for v in d.values() if v["material_guess"].strip() in UNKNOWN_MATERIAL)
        c = cost.get(m, {})
        L.append("| %s | %.1f | %d / %d | $%.3f |" % (LABEL.get(m, m), statistics.mean(len(v["tags"]) for v in d.values()),
                                                     unk, len(d), c.get("cost_usd_total", c.get("cost_usd", 0))))
    L += ["", "> 아이콘이 흑백 실루엣이라 재질 정보는 이미지에 **없다**. '불명'으로 남긴 비율이 높을수록 "
              "모르는 것을 지어내지 않았다는 뜻이다. 비용에는 데이터셋 개정에 따른 재라벨링이 포함돼 있다.", ""]
    if len(models) >= 2:
        a, b = models[0], models[1]
        ks = sorted(set(raw[a]) & set(raw[b]))
        L += ["두 모델이 같은 아이콘에 붙인 **태그의 자카드 유사도 평균은 %.2f** 다(1.0 = 완전 일치). "
              "같은 그림을 거의 다른 단어로 적는다 — 어느 모델로 라벨을 만드느냐가 검색 결과를 바꾼다. "
              "(어휘 겹침이지 정오가 아니다.)" % statistics.mean(jaccard(raw[a][k]["tags"], raw[b][k]["tags"]) for k in ks), ""]
    jc = RESULTS / "judge.cost.json"
    if jc.exists():
        L += ["판정 비용: $%.3f (Opus 5, %d쌍)." % (json.loads(jc.read_text(encoding="utf-8"))["cost_usd_total"], len(verdicts)), ""]

    path = RESULTS / "label_comparison.md"
    path.write_text("\n".join(L), encoding="utf-8")
    print("작성: results/label_comparison.md (%d줄)" % len(L))


if __name__ == "__main__":
    main()
