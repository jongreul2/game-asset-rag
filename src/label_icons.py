# -*- coding: utf-8 -*-
"""① 자동 라벨링 — 아이콘 이미지만 보고 구조화된 라벨(JSON)을 만든다.

⛔ 설계상 가장 중요한 제약: **모델에게 아이템 이름·설명·태그를 주지 않는다.**
   설명을 같이 주면 모델이 그것을 바꿔 쓴 라벨이 나오고, 조건 B(텍스트+자동 라벨)는
   조건 A(텍스트만)를 그대로 복제한 것이 되어 비교 자체가 무의미해진다.
   라벨은 오직 이미지에서만 나와야 한다.

사용:
    python src/label_icons.py --model claude-sonnet-5            # 배치(50% 할인)
    python src/label_icons.py --model claude-haiku-4-5 --limit 5 --sync   # 소량 확인용
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import RESULTS, Usage, icon_b64, items, require_key, save_jsonl  # noqa: E402

SYSTEM = (
    "너는 게임 아이템 아이콘을 보고 검색용 메타데이터를 만드는 주석 작업자다. "
    "보이는 것만 적는다. 아이콘은 흑백 실루엣이므로 색과 재질은 대부분 알 수 없다 — "
    "추측이 근거 없으면 material_guess 를 '불명'으로 둔다. "
    "무엇인지 확실하지 않으면 확실한 척하지 말고 보이는 형태로 기술한다. "
    "게임 이름이나 특정 IP를 언급하지 않는다. 모든 값은 한국어로 쓴다.\n"
    "⛔ tags 규칙: 이 아이콘을 **다른 아이콘과 구별해 주는 단어만** 넣는다. "
    "'아이콘', '실루엣', '흑백', '게임아이템', '이미지', '장비' 처럼 모든 아이콘에 해당하는 "
    "일반어는 검색에서 변별력이 0이므로 절대 넣지 않는다. "
    "object_kind 는 문장이 아니라 짧은 명사구로 쓴다."
)

USER_TEXT = (
    "이 아이콘에 무엇이 그려져 있는지 기술하라. 아이템의 이름·설명은 주어지지 않으며, "
    "오직 이미지에서 읽히는 것만 적는다."
)

LABEL_SCHEMA = {
    "type": "object",
    "properties": {
        "object_kind": {"type": "string", "description": "무엇을 그린 것인가 (예: 한손 검, 원형 방패, 유리병)"},
        "shape": {"type": "string", "description": "전체 형태 (예: 길쭉하고 곧은 날, 둥근 판)"},
        "components": {
            "type": "array", "items": {"type": "string"},
            "description": "눈에 보이는 구성 요소 2~6개 (예: 손잡이, 날, 사슬)",
        },
        "material_guess": {"type": "string", "description": "재질 추정. 근거가 없으면 '불명'"},
        "likely_use": {"type": "string", "description": "이 물건의 쓰임새 추정"},
        "tags": {
            "type": "array", "items": {"type": "string"},
            "description": "검색용 한국어 태그 5~10개",
        },
        "one_line": {"type": "string", "description": "한 문장 설명"},
    },
    "required": ["object_kind", "shape", "components", "material_guess", "likely_use", "tags", "one_line"],
    "additionalProperties": False,
}

OUTPUT_CONFIG = {"format": {"type": "json_schema", "schema": LABEL_SCHEMA}}
MAX_TOKENS = 1024


def build_content(item: dict) -> list[dict]:
    return [
        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": icon_b64(item)}},
        {"type": "text", "text": USER_TEXT},
    ]


def request_params(item: dict, model: str) -> dict:
    params = {
        "model": model,
        "max_tokens": MAX_TOKENS,
        "system": SYSTEM,
        "messages": [{"role": "user", "content": build_content(item)}],
        "output_config": OUTPUT_CONFIG,
    }
    # 라벨링은 추론이 필요한 작업이 아니다. 끌 수 있는 모델에서는 꺼서 비용·지연을 줄인다.
    # (Haiku 4.5 는 thinking 을 지정하지 않으면 애초에 동작하지 않는다.)
    if model == "claude-sonnet-5":
        params["thinking"] = {"type": "disabled"}
    return params


def parse_label(message) -> dict:
    text = next(b.text for b in message.content if b.type == "text")
    return json.loads(text)


def run_sync(client, rows: list[dict], model: str) -> tuple[list[dict], Usage]:
    usage, out = Usage(), []
    for it in rows:
        msg = client.messages.create(**request_params(it, model))
        usage.add(msg.usage)
        out.append({"item_id": it["id"], "icon": it["icon"], "model": model, "label": parse_label(msg)})
        print("  %s %s" % (it["id"], out[-1]["label"]["object_kind"]))
    return out, usage


def run_batch(client, rows: list[dict], model: str, poll: int = 30) -> tuple[list[dict], Usage]:
    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
    from anthropic.types.messages.batch_create_params import Request

    batch = client.messages.batches.create(
        requests=[
            Request(custom_id=it["id"], params=MessageCreateParamsNonStreaming(**request_params(it, model)))
            for it in rows
        ]
    )
    print("배치 생성: %s (%d건)" % (batch.id, len(rows)))

    while True:
        batch = client.messages.batches.retrieve(batch.id)
        if batch.processing_status == "ended":
            break
        print("  상태 %s · 처리중 %s" % (batch.processing_status, batch.request_counts.processing))
        time.sleep(poll)
    print("완료: 성공 %d · 실패 %d" % (batch.request_counts.succeeded, batch.request_counts.errored))

    by_id = {it["id"]: it for it in rows}
    usage, out, failed = Usage(), [], []
    # 결과는 순서를 보장하지 않는다 — 반드시 custom_id 로 매칭한다.
    for res in client.messages.batches.results(batch.id):
        if res.result.type == "succeeded":
            msg = res.result.message
            usage.add(msg.usage)
            it = by_id[res.custom_id]
            try:
                label = parse_label(msg)
            except (StopIteration, json.JSONDecodeError) as e:
                failed.append({"item_id": res.custom_id, "reason": "parse: %s" % e})
                continue
            out.append({"item_id": it["id"], "icon": it["icon"], "model": model, "label": label})
        else:
            failed.append({"item_id": res.custom_id, "reason": res.result.type})
    if failed:
        print("⚠ 실패 %d건: %s" % (len(failed), failed[:5]))
    out.sort(key=lambda r: r["item_id"])
    return out, usage


def collect_batch(client, batch_id: str, rows: list[dict], model: str) -> tuple[list[dict], Usage]:
    """이미 끝난 배치에서 결과만 회수한다. 결과는 29일간 보관되므로
    폴링하던 프로세스가 죽어도 배치 ID만 있으면 언제든 되찾을 수 있다."""
    by_id = {it["id"]: it for it in rows}
    usage, out, failed = Usage(), [], []
    for res in client.messages.batches.results(batch_id):
        if res.result.type != "succeeded":
            failed.append({"item_id": res.custom_id, "reason": res.result.type})
            continue
        msg = res.result.message
        usage.add(msg.usage)
        try:
            label = parse_label(msg)
        except (StopIteration, json.JSONDecodeError) as e:
            failed.append({"item_id": res.custom_id, "reason": "parse: %s" % e})
            continue
        it = by_id[res.custom_id]
        out.append({"item_id": it["id"], "icon": it["icon"], "model": model, "label": label})
    if failed:
        print("⚠ 실패 %d건: %s" % (len(failed), failed[:5]))
    out.sort(key=lambda r: r["item_id"])
    return out, usage


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="claude-sonnet-5",
                    choices=["claude-sonnet-5", "claude-haiku-4-5", "claude-opus-5"])
    ap.add_argument("--limit", type=int, default=0, help="앞에서 N건만 (0=전체)")
    ap.add_argument("--sync", action="store_true", help="배치 대신 동기 호출(할인 없음, 소량 확인용)")
    ap.add_argument("--fetch", metavar="BATCH_ID",
                    help="이미 제출한 배치의 결과만 회수(폴링 프로세스가 죽었을 때). "
                         "--model 은 결과 파일명·비용 계산에 쓰이므로 제출 때와 같게 준다")
    ap.add_argument("--status", action="store_true", help="최근 배치 상태만 조회하고 종료")
    args = ap.parse_args()

    if args.status:
        require_key("ANTHROPIC_API_KEY")
        import anthropic
        for b in anthropic.Anthropic().messages.batches.list(limit=10):
            rc = b.request_counts
            print("%s | %s | 처리중 %d · 성공 %d · 실패 %d | %s"
                  % (b.id, b.processing_status, rc.processing, rc.succeeded, rc.errored, b.created_at))
        return

    require_key("ANTHROPIC_API_KEY")
    import anthropic

    client = anthropic.Anthropic()
    rows = items()
    if args.limit:
        rows = rows[: args.limit]

    if args.fetch:
        print("배치 결과 회수: %s (%s)" % (args.fetch, args.model))
        out, usage = collect_batch(client, args.fetch, rows, args.model)
    else:
        print("자동 라벨링: %s · %d건 · %s" % (args.model, len(rows), "동기" if args.sync else "배치"))
        runner = run_sync if args.sync else run_batch
        out, usage = runner(client, rows, args.model)

    tag = args.model.replace("claude-", "")
    save_jsonl(RESULTS / ("labels_%s.jsonl" % tag), out)
    report = usage.report(args.model, batch=not args.sync)
    (RESULTS / ("labels_%s.cost.json" % tag)).write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("저장: results/labels_%s.jsonl · 비용 %s" % (tag, report))


if __name__ == "__main__":
    main()
