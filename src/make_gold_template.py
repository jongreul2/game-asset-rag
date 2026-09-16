# -*- coding: utf-8 -*-
"""라벨 정답셋(사람이 작성) 템플릿 + 대조용 컨택트 시트를 만든다.

라벨 품질 평가의 기준선은 **사람이 만든 정답**이어야 한다. 모델이 만든 라벨을
다른 모델로 채점하면 모델끼리 비교하는 것이 되어 기준선이 되지 못한다.
이 스크립트는 채울 칸과 아이콘 모음 이미지를 만들어 주는 것까지만 한다.

사용:
    python src/make_gold_template.py            # 50건 층화 추출
    python src/make_gold_template.py --n 20     # 개수 조정
"""
from __future__ import annotations

import argparse
import random
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DATA, EVAL, OUT, items, save_jsonl  # noqa: E402

# 분류 비율을 전체 데이터와 맞춘다(무기 40/방어구 35/장신구 15/소비 25/재료 20/도구 15 → 150건)
SEED = 20260916


def stratified(rows: list[dict], n: int) -> list[dict]:
    by_cat: dict[str, list[dict]] = {}
    for it in rows:
        by_cat.setdefault(it["category"], []).append(it)
    rng = random.Random(SEED)
    picked: list[dict] = []
    for cat, group in sorted(by_cat.items()):
        k = max(1, round(n * len(group) / len(rows)))
        picked += rng.sample(sorted(group, key=lambda d: d["id"]), min(k, len(group)))
    picked.sort(key=lambda d: d["id"])
    return picked[:n]


def contact_sheet(picked: list[dict], path: Path, cols: int = 10, cell: int = 128) -> None:
    from PIL import Image, ImageDraw

    rows = (len(picked) + cols - 1) // cols
    pad = 18
    sheet = Image.new("RGB", (cols * cell, rows * (cell + pad)), "white")
    draw = ImageDraw.Draw(sheet)
    for i, it in enumerate(picked):
        x, y = (i % cols) * cell, (i // cols) * (cell + pad)
        icon = Image.open(DATA / "icons" / it["icon"]).convert("RGB").resize((cell, cell))
        sheet.paste(icon, (x, y))
        draw.text((x + 3, y + cell + 3), it["id"].replace("itm_", ""), fill="black")
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(path)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=50)
    args = ap.parse_args()

    rows = items()
    picked = stratified(rows, args.n)

    template = [
        {
            "item_id": it["id"],
            "icon": it["icon"],
            # ↓ 사람이 채운다. 아이콘만 보고 쓰고, 아이템 이름·설명은 보지 않는다.
            "object_kind": "",
            "shape": "",
            "components": [],
            "material_guess": "",
            "likely_use": "",
            "tags": [],
        }
        for it in picked
    ]
    save_jsonl(EVAL / "label_gold.jsonl", template)
    contact_sheet(picked, OUT / "contact_sheet_gold.png")

    print("정답 라벨 템플릿 %d건 → eval/label_gold.jsonl" % len(template))
    print("대조용 아이콘 모음 → out/contact_sheet_gold.png")
    print("분류 분포:", dict(Counter(it["category"] for it in picked)))
    print("\n작성 요령: 컨택트 시트를 보고 칸을 채운다. 아이템 이름·설명은 보지 않는다")
    print("(보면 정답이 설명문을 따라가고, 이미지만 본 모델과 비교할 수 없게 된다).")


if __name__ == "__main__":
    main()
