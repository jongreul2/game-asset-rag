# -*- coding: utf-8 -*-
"""라벨 채점 — 정답은 **아이콘 원작자가 붙인 이름**(data/icon_map.csv 의 icon_name)이다.

정답(영문 슬러그)과 답(한국어)은 글자 비교가 안 되므로, "같은 물건을 가리키는가"를
LLM 판정관이 3단계로 판정한다. 판정관이 믿을 만한지는 사람이 무작위 표본을 따로
채점해 일치율로 확인한다(src/make_judge_check_tool.py → compare_labels.py).

공정성 장치:
- 판정관은 답의 출처(사람/어느 모델)를 모른다. 쌍을 섞어서 준다.
- (정답, 답) 문자열이 같은 쌍은 한 번만 판정한다 → 같은 답에는 같은 판정이 보장된다.
- 판정 기준(루브릭)은 아래 SYSTEM 에 고정돼 있고 결과 파일에 함께 기록된다.

한계: 판정관(Opus 5)과 채점 대상(Sonnet 5 · Haiku 4.5)이 같은 계열이다. 출처를 가렸고
과제가 '같은 물건인가'라는 사실 판단이라 자기선호 편향의 여지는 작지만 0은 아니다.

사용:
    python src/judge_labels.py            # 새 쌍만 판정(이미 판정한 쌍은 건너뜀)
"""
from __future__ import annotations

import csv
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DATA, EVAL, RESULTS, Usage, load_jsonl, require_key  # noqa: E402

JUDGE_MODEL = "claude-opus-5"
CHUNK = 25
SEED = 20260917
VERDICTS_PATH = EVAL / "judge_verdicts.json"

SYSTEM = """너는 아이콘 라벨 채점관이다. 각 항목에는 (1) 아이콘 원작자가 붙인 영문 이름과
(2) 누군가 그 아이콘을 보고 적은 한국어 답이 있다. 답이 원작자 이름과 **같은 물건**을 가리키는지 판정한다.

판정 기준
- match  : 같은 종류의 물건이다. 동의어, 더 구체적인 표현, 한 단계 일반적인 표현을 포함한다.
           (예: boots ↔ 신발/부츠 한 쌍, stiletto ↔ 단검, health-potion ↔ 물약병/포션)
- partial: 큰 범주는 같지만 다른 물건이다. (예: dagger ↔ 검, ring ↔ 팔찌, helmet ↔ 갑옷)
- miss   : 다른 물건이다. 또는 답이 '모르겠음', '?' 처럼 판독 포기다.

주의
- 원작자 이름의 수식어(효과·상태·장식)는 무시하고 **핵심 물건**만 본다.
  (예: bloody-sword 의 핵심은 sword, potion-of-madness 의 핵심은 potion, fish-smoking 의 핵심은 fish)
- 답이 길어도 핵심 물건이 맞으면 match 다. 답에 물건이 여러 개면 중심이 되는 물건으로 판정한다.
- 답을 쓴 주체가 누구인지는 주어지지 않으며 추측하지 않는다."""

SCHEMA = {
    "type": "object",
    "properties": {
        "verdicts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "verdict": {"type": "string", "enum": ["match", "partial", "miss"]},
                    "reason": {"type": "string", "description": "한 줄 근거"},
                },
                "required": ["id", "verdict", "reason"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["verdicts"],
    "additionalProperties": False,
}


def pair_key(icon_name: str, answer: str) -> str:
    return icon_name.strip() + " ||| " + answer.strip()


def answer_key() -> dict[str, str]:
    """item_id → 원작자 아이콘 이름"""
    with open(DATA / "icon_map.csv", encoding="utf-8", newline="") as f:
        return {r["item_id"]: r["icon_name"] for r in csv.DictReader(f)}


def sources() -> dict[str, dict[str, str]]:
    """출처별 {item_id: 답}. 사람 답은 eval/label_gold.jsonl(빈 칸 제외)."""
    out: dict[str, dict[str, str]] = {}
    for p in sorted(RESULTS.glob("labels_*.jsonl")):
        out[p.stem.replace("labels_", "")] = {r["item_id"]: r["label"]["object_kind"] for r in load_jsonl(p)}
    human = {r["item_id"]: r["object_kind"] for r in load_jsonl(EVAL / "label_gold.jsonl")
             if r.get("object_kind", "").strip()}
    out["human"] = human
    return out


def load_verdicts() -> dict[str, dict]:
    return json.loads(VERDICTS_PATH.read_text(encoding="utf-8")) if VERDICTS_PATH.exists() else {}


def main() -> None:
    key = answer_key()
    done = load_verdicts()
    pairs: dict[str, tuple[str, str]] = {}
    for answers in sources().values():
        for item_id, ans in answers.items():
            k = pair_key(key[item_id], ans)
            if k not in done:
                pairs[k] = (key[item_id], ans)
    todo = sorted(pairs.items())
    random.Random(SEED).shuffle(todo)          # 출처·아이템 순서가 드러나지 않게 섞는다
    print("판정할 새 쌍 %d개 (기존 %d개는 건너뜀)" % (len(todo), len(done)))
    if not todo:
        return

    require_key("ANTHROPIC_API_KEY")
    import anthropic
    client = anthropic.Anthropic()
    usage = Usage()

    for start in range(0, len(todo), CHUNK):
        chunk = todo[start:start + CHUNK]
        lines = ["%d. 원작자 이름: %s | 답: %s" % (i, name, ans) for i, (_, (name, ans)) in enumerate(chunk)]
        msg = client.messages.create(
            model=JUDGE_MODEL,
            max_tokens=8000,
            system=SYSTEM,
            messages=[{"role": "user", "content": "다음 %d개를 판정하라.\n\n%s" % (len(chunk), "\n".join(lines))}],
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
        )
        if msg.stop_reason != "end_turn":
            raise SystemExit("판정 중단: stop_reason=%s" % msg.stop_reason)
        usage.add(msg.usage)
        verdicts = json.loads(next(b.text for b in msg.content if b.type == "text"))["verdicts"]
        got = {v["id"]: v for v in verdicts}
        if set(got) != set(range(len(chunk))):
            raise SystemExit("판정 누락: 받은 id %s" % sorted(got))
        for i, (k, (name, ans)) in enumerate(chunk):
            done[k] = {"icon_name": name, "answer": ans, "verdict": got[i]["verdict"], "reason": got[i]["reason"]}
        VERDICTS_PATH.write_text(json.dumps(done, ensure_ascii=False, indent=1), encoding="utf-8")
        print("  %d / %d" % (min(start + CHUNK, len(todo)), len(todo)))

    report = usage.report(JUDGE_MODEL, batch=False)
    cost_path = RESULTS / "judge.cost.json"
    prev = json.loads(cost_path.read_text(encoding="utf-8")) if cost_path.exists() else {"runs": []}
    prev["runs"].append(report)
    prev["cost_usd_total"] = round(sum(r["cost_usd"] for r in prev["runs"]), 4)
    cost_path.write_text(json.dumps(prev, ensure_ascii=False, indent=2), encoding="utf-8")
    print("판정 완료 · 이번 비용 $%.4f · 누적 $%.4f" % (report["cost_usd"], prev["cost_usd_total"]))


if __name__ == "__main__":
    main()
