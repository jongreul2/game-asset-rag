# -*- coding: utf-8 -*-
"""공통 경로·데이터 로딩·비용 계산."""
from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
EVAL = ROOT / "eval"
OUT = ROOT / "out"          # 스크래치(gitignore) — 컨택트 시트 등
RESULTS = ROOT / "results"  # 커밋하는 실험 결과

# 2026-09-16 공식 가격표(USD / 100만 토큰) 기준. Batch API 는 입·출력 모두 50%.
# 출처: https://platform.claude.com/docs/en/about-claude/pricing
PRICING = {
    "claude-opus-5":   {"in": 5.00, "out": 25.00},
    "claude-sonnet-5": {"in": 2.00, "out": 10.00},
    "claude-haiku-4-5": {"in": 1.00, "out": 5.00},
}


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    requests: int = 0

    def add(self, u) -> None:
        self.input_tokens += u.input_tokens
        self.output_tokens += u.output_tokens
        self.requests += 1

    def cost_usd(self, model: str, batch: bool = True) -> float:
        p = PRICING[model]
        usd = self.input_tokens / 1e6 * p["in"] + self.output_tokens / 1e6 * p["out"]
        return usd * (0.5 if batch else 1.0)

    def report(self, model: str, batch: bool = True) -> dict:
        return {
            "model": model,
            "batch": batch,
            "requests": self.requests,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost_usd": round(self.cost_usd(model, batch), 4),
        }


def load_jsonl(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def save_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def items() -> list[dict]:
    return load_jsonl(DATA / "items.jsonl")


def quests() -> list[dict]:
    return load_jsonl(DATA / "quests.jsonl")


def icon_b64(item: dict) -> str:
    """아이콘 PNG 를 base64 로 읽는다."""
    with open(DATA / "icons" / item["icon"], "rb") as f:
        return base64.standard_b64encode(f.read()).decode("utf-8")


def load_env() -> None:
    """.env 를 읽어 환경변수에 넣는다(저장소에 커밋되지 않는 파일)."""
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def require_key(name: str) -> str:
    load_env()
    v = os.environ.get(name)
    if not v:
        raise SystemExit(
            "환경변수 %s 가 없다. 저장소 루트에 .env 를 만들고 %s=... 를 넣어라(.gitignore 됨)." % (name, name)
        )
    return v
