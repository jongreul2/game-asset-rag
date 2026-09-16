# -*- coding: utf-8 -*-
"""아이템 150건에 game-icons.net 아이콘을 매핑·추출하고 items.jsonl / icon_map.csv / ATTRIBUTION.md 를 갱신한다.

아이콘 아카이브(29MB)는 저장소에 넣지 않는다. 아래에서 받는다:
    curl -L -o game-icons.zip "https://game-icons.net/archives/png/zip/000000/ffffff/game-icons.net.png.zip"

사용:
    python src/build_icon_map.py path/to/game-icons.zip

매핑은 사람이 아이콘을 눈으로 보고 골랐다(아이템당 1개, 중복 사용 없음).
검증은 fail-fast 다 — 오타·미매핑·중복·아카이브 부재가 하나라도 있으면 아무것도 쓰지 않고 종료한다.
"""
from __future__ import annotations

import collections
import csv
import io
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

MAP = {
    # --- 무기 ---
    "itm_w001": "rusty-sword",       "itm_w002": "broadsword",
    "itm_w003": "piercing-sword",    "itm_w004": "bloody-sword",
    "itm_w005": "shining-sword",     "itm_w006": "striped-sword",
    "itm_w007": "energy-sword",      "itm_w008": "two-handed-sword",
    "itm_w009": "shattered-sword",   "itm_w010": "pointy-sword",
    "itm_w011": "sword-brandish",    "itm_w012": "relic-blade",
    "itm_w013": "wood-axe",          "itm_w014": "battle-axe",
    "itm_w015": "war-axe",           "itm_w016": "sharp-axe",
    "itm_w017": "battered-axe",      "itm_w018": "wood-club",
    "itm_w019": "flanged-mace",      "itm_w020": "thor-hammer",
    "itm_w021": "warhammer",         "itm_w022": "wood-stick",
    "itm_w023": "plain-dagger",      "itm_w024": "bone-knife",
    "itm_w025": "cloak-dagger",      "itm_w026": "sacrificial-dagger",
    "itm_w027": "daggers",           "itm_w028": "bowie-knife",
    "itm_w029": "pocket-bow",        "itm_w030": "bow-arrow",
    "itm_w031": "crossbow",          "itm_w032": "harpoon-chain",
    "itm_w033": "bow-string",        "itm_w034": "wizard-staff",
    "itm_w035": "crescent-staff",    "itm_w036": "winged-scepter",
    "itm_w037": "skull-staff",       "itm_w038": "crystal-wand",
    "itm_w039": "rod-of-asclepius",  "itm_w040": "orb-wand",
    # --- 방어구 ---
    "itm_a001": "round-shield",      "itm_a002": "roman-shield",
    "itm_a003": "turtle-shell",      "itm_a004": "fire-shield",
    "itm_a005": "ice-shield",        "itm_a006": "templar-shield",
    "itm_a007": "shield-reflect",    "itm_a008": "crenulated-shield",
    "itm_a009": "hood",              "itm_a010": "helmet",
    "itm_a011": "horned-helm",       "itm_a012": "diving-helmet",
    "itm_a013": "skull-mask",        "itm_a014": "crown",
    "itm_a015": "cracked-helm",      "itm_a016": "shirt",
    "itm_a017": "mail-shirt",        "itm_a018": "leather-armor",
    "itm_a019": "breastplate",       "itm_a020": "pirate-coat",
    "itm_a021": "robe",              "itm_a022": "layered-armor",
    "itm_a023": "cloak",             "itm_a024": "gloves",
    "itm_a025": "gauntlet",          "itm_a026": "winter-gloves",
    "itm_a027": "mailed-fist",       "itm_a028": "hand-bandage",
    "itm_a029": "hand-of-god",       "itm_a030": "tabi-boot",
    "itm_a031": "leather-boot",      "itm_a032": "walking-boot",
    "itm_a033": "steeltoe-boots",    "itm_a034": "sticky-boot",
    "itm_a035": "metal-boot",
    # --- 장신구 ---
    "itm_c001": "ring",              "itm_c002": "swirl-ring",
    "itm_c003": "diamond-ring",      "itm_c004": "frozen-ring",
    "itm_c005": "power-ring",        "itm_c006": "linked-rings",
    "itm_c007": "primitive-necklace", "itm_c008": "gem-pendant",
    "itm_c009": "necklace",          "itm_c010": "compass",
    "itm_c011": "pendant-key",       "itm_c012": "holy-symbol",
    "itm_c013": "frog-foot",         "itm_c014": "covered-jar",
    "itm_c015": "skull-signet",
    # --- 소비품: 물약 ---
    "itm_p001": "standing-potion",   "itm_p002": "health-potion",
    "itm_p003": "round-potion",      "itm_p004": "magic-potion",
    "itm_p005": "spiral-bottle",     "itm_p006": "fizzing-flask",
    "itm_p007": "fire-bottle",       "itm_p008": "snow-bottle",
    "itm_p009": "bottled-shadow",    "itm_p010": "bubbling-flask",
    "itm_p011": "heart-bottle",      "itm_p012": "potion-of-madness",
    # --- 소비품: 음식 ---
    "itm_f001": "bread",             "itm_f002": "fish-smoking",
    "itm_f003": "camp-cooking-pot",  "itm_f004": "chili-pepper",
    "itm_f005": "cookie",            "itm_f006": "beer-stein",
    "itm_f007": "elderberry",
    # --- 소비품: 주문서 ---
    "itm_s001": "tied-scroll",       "itm_s002": "scroll-unfurled",
    "itm_s003": "scroll-quill",      "itm_s004": "papers",
    "itm_s005": "folded-paper",      "itm_s006": "spell-book",
    # --- 재료 ---
    "itm_m001": "animal-hide",       "itm_m002": "rolled-cloth",
    "itm_m003": "armoured-shell",    "itm_m004": "ore",
    "itm_m005": "gold-bar",          "itm_m006": "minerals",
    "itm_m007": "crystal-growth",    "itm_m008": "floating-crystal",
    "itm_m009": "spider-web",        "itm_m010": "sewing-string",
    "itm_m011": "spotted-mushroom",  "itm_m012": "herbs-bundle",
    "itm_m013": "bell-pepper",       "itm_m014": "leaf-swirl",
    "itm_m015": "powder",            "itm_m016": "metal-scales",
    "itm_m017": "salt-shaker",       "itm_m018": "sword-break",
    "itm_m019": "earth-worm",        "itm_m020": "broken-tablet",
    # --- 도구 ---
    "itm_t001": "primitive-torch",   "itm_t002": "old-lantern",
    "itm_t003": "mining",            "itm_t004": "war-pick",
    "itm_t005": "sickle",            "itm_t006": "fishing-pole",
    "itm_t007": "needle-drill",      "itm_t008": "rope-coil",
    "itm_t009": "grapple",           "itm_t010": "lockpicks",
    "itm_t011": "camping-tent",      "itm_t012": "mantrap",
    "itm_t013": "treasure-map",      "itm_t014": "maze",
    "itm_t015": "key",
}

NL = "\n"


def write_attribution(rows: list[dict]) -> None:
    by: dict[str, list[str]] = collections.defaultdict(list)
    for r in rows:
        by[r["icon_author"]].append(r["icon_name"])
    L = ["# 아이콘 출처 표기" + NL]
    L.append("이 폴더의 PNG %d개는 [game-icons.net](https://game-icons.net) 아이콘이며 "
             "**Creative Commons 3.0 BY** 라이선스로 배포된다." % len(rows))
    L.append("원본 아카이브(검은색 전경 / 흰색 배경 512px PNG)에서 추출했고, 파일명만 "
             "`<item_id>_<icon_name>.png` 형식으로 바꿨다. 이미지 자체는 수정하지 않았다." + NL)
    L.append("아이템별 대응은 [`../icon_map.csv`](../icon_map.csv) 에 있다." + NL)
    L.append("## 원작자별 목록" + NL)
    for a in sorted(by, key=lambda k: (-len(by[k]), k)):
        L.append("### %s (%d개)%s" % (a, len(by[a]), NL))
        L.append("> Icons made by %s. Available on https://game-icons.net%s" % (a, NL))
        L.append(", ".join("`%s`" % n for n in sorted(by[a])) + NL)
    with io.open(DATA / "icons" / "ATTRIBUTION.md", "w", encoding="utf-8", newline=NL) as f:
        f.write(NL.join(L))


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("사용: python src/build_icon_map.py <game-icons.net.png.zip>")
    z = zipfile.ZipFile(sys.argv[1])

    index: dict[str, list[str]] = {}
    for n in z.namelist():
        if n.endswith(".png"):
            index.setdefault(n.split("/")[-1][:-4], []).append(n)

    with io.open(DATA / "items.jsonl", encoding="utf-8") as f:
        items = [json.loads(l) for l in f if l.strip()]
    ids = {d["id"] for d in items}

    problems = [
        ("아카이브에 없는 아이콘", [(i, v) for i, v in MAP.items() if v not in index]),
        ("존재하지 않는 아이템 id", [i for i in MAP if i not in ids]),
        ("아이콘 없는 아이템", [i for i in ids if i not in MAP]),
        ("중복 사용 아이콘", [v for v, c in collections.Counter(MAP.values()).items() if c > 1]),
    ]
    for label, val in problems:
        if val:
            raise SystemExit("[FAIL] %s: %s" % (label, val))

    outdir = DATA / "icons"
    outdir.mkdir(parents=True, exist_ok=True)
    rows = []
    for d in items:
        name = MAP[d["id"]]
        path = sorted(index[name])[0]        # 동명(작가 여럿)이면 사전순 첫 번째로 고정 → 재현성
        author = path.split("/")[-2]
        fname = "%s_%s.png" % (d["id"], name)
        (outdir / fname).write_bytes(z.read(path))
        d["icon"], d["icon_author"] = fname, author
        rows.append({"item_id": d["id"], "item_name": d["name"], "icon_file": fname,
                     "icon_name": name, "icon_author": author,
                     "source": "https://game-icons.net", "license": "CC BY 3.0"})

    with io.open(DATA / "items.jsonl", "w", encoding="utf-8", newline=NL) as f:
        for d in items:
            f.write(json.dumps(d, ensure_ascii=False) + NL)
    with io.open(DATA / "icon_map.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    write_attribution(rows)
    print("아이콘 %d개 추출 · 원작자 %d명" % (len(rows), len({r["icon_author"] for r in rows})))


if __name__ == "__main__":
    main()
