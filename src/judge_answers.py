# -*- coding: utf-8 -*-
"""답변 충실도 판정 — 답에 들어 있는 주장이 검색된 문서로 뒷받침되는가.

답변 하나를 사실 주장 단위로 쪼개고, 주장마다 그 답변 모델이 실제로 받은 문서 5개와 대조한다.
  supported    문서에 그대로 있거나 문서의 수치·문장에서 바로 따라 나온다
  unsupported  문서에 없거나 문서와 어긋난다
"문서에 ○○은 없다"는 말도 주장으로 센다 — 문서 5개에 정말 없으면 supported 다.
인사말·말투·"도움이 되길" 같은 문장은 주장이 아니다.

공정성 장치: 판정관은 어느 모델의 답인지 모른다(입력에 모델 이름이 없다). 판정 기준은 아래 SYSTEM 에
고정돼 있다. 한계: 판정관(Opus 5)이 답변 모델과 같은 계열이고, 이 판정은 사람 표본 검증을 거치지 않았다.
그래서 unsupported 로 찍힌 주장은 리포트에 전부 원문으로 싣는다 — 읽는 사람이 직접 확인할 수 있다.

사용:
    python src/judge_answers.py                     # results/answers_*.jsonl 전부, 새 답만 판정
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import RESULTS, Usage, load_jsonl, require_key  # noqa: E402
from rag import CORPUS, docs_block  # noqa: E402
from search_eval import build_corpora  # noqa: E402

JUDGE_MODEL = "claude-opus-5"
VERDICTS_PATH = RESULTS / "answer_verdicts.json"

SYSTEM = """너는 검색 기반 답변의 충실도 채점관이다. <docs> 는 답변자가 받은 문서 전부이고, <answer> 는 그 답변이다.

할 일
1. 답변을 사실 주장 단위로 쪼갠다. 한 주장 = 확인 가능한 사실 하나(아이템의 존재·이름·수치·등급·지역·효과·설정, 퀘스트의 의뢰인·목표·보상 등).
   인사말, 말투, 권유("추천합니다"), 질문 되풀이는 주장이 아니다.
2. 주장마다 문서와 대조해 판정한다.
   - supported  : 문서에 그대로 있거나, 문서의 수치·문장에서 바로 따라 나온다(예: 요구 레벨 비교, 개수 세기).
   - unsupported: 문서에 없다. 또는 문서와 어긋난다(수치·이름·지역이 다름).
3. "문서에 ○○은 없다"는 말도 주장이다. 문서 5개 안에 정말 없으면 supported, 있는데 없다고 했으면 unsupported.

주의
- 문서 밖의 상식이나 다른 게임 지식으로 맞다고 봐주지 않는다. 기준은 오직 <docs> 다.
- 문서의 "[아이콘에서 읽은 정보]" 도 문서의 일부다. 거기 적힌 내용을 옮긴 주장은 supported 다.
- 한 문장에 수치가 여러 개면 수치마다 따로 센다. 하나라도 틀리면 그 주장만 unsupported 다."""

SCHEMA = {
    "type": "object",
    "properties": {
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "claim": {"type": "string"},
                    "verdict": {"type": "string", "enum": ["supported", "unsupported"]},
                    "reason": {"type": "string", "description": "근거 문서 id 와 한 줄 이유"},
                },
                "required": ["claim", "verdict", "reason"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["claims"],
    "additionalProperties": False,
}


def main() -> None:
    _, corp, _ = build_corpora()
    docs = corp[CORPUS]
    done = json.loads(VERDICTS_PATH.read_text(encoding="utf-8")) if VERDICTS_PATH.exists() else {}

    todo = []
    for p in sorted(RESULTS.glob("answers_*.jsonl")):
        tag = p.stem.replace("answers_", "")
        for r in load_jsonl(p):
            key = "%s|%s" % (tag, r["qid"])
            if key not in done and r["stop_reason"] == "end_turn":
                todo.append((key, r))
    print("판정할 답변 %d개 (기존 %d개는 건너뜀)" % (len(todo), len(done)))
    if not todo:
        return

    require_key("ANTHROPIC_API_KEY")
    import anthropic
    client = anthropic.Anthropic()
    usage = Usage()

    for n, (key, r) in enumerate(todo, 1):
        hits = [{"id": i, "text": docs[i]} for i in r["retrieved_ids"]]
        msg = client.messages.create(
            model=JUDGE_MODEL,
            max_tokens=8000,
            system=SYSTEM,
            messages=[{"role": "user", "content": "%s\n\n질문: %s\n\n<answer>\n%s\n</answer>"
                       % (docs_block(hits), r["query"], r["answer"])}],
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
        )
        if msg.stop_reason != "end_turn":
            raise SystemExit("판정 중단(%s): stop_reason=%s" % (key, msg.stop_reason))
        usage.add(msg.usage)
        claims = json.loads(next(b.text for b in msg.content if b.type == "text"))["claims"]
        done[key] = {"qid": r["qid"], "claims": claims}
        VERDICTS_PATH.write_text(json.dumps(done, ensure_ascii=False, indent=1), encoding="utf-8")
        bad = sum(c["verdict"] == "unsupported" for c in claims)
        print("  %d / %d  %s  주장 %d개 · 근거 없음 %d개" % (n, len(todo), key, len(claims), bad))

    report = usage.report(JUDGE_MODEL, batch=False)
    cost_path = RESULTS / "answer_judge.cost.json"
    prev = json.loads(cost_path.read_text(encoding="utf-8")) if cost_path.exists() else {"runs": []}
    prev["runs"].append(report)
    prev["cost_usd_total"] = round(sum(x["cost_usd"] for x in prev["runs"]), 4)
    cost_path.write_text(json.dumps(prev, ensure_ascii=False, indent=2), encoding="utf-8")
    print("판정 완료 · 이번 비용 $%.4f · 누적 $%.4f" % (report["cost_usd"], prev["cost_usd_total"]))


if __name__ == "__main__":
    main()
