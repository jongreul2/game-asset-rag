# -*- coding: utf-8 -*-
"""검색 정답셋(eval/golden_queries.jsonl)을 만든다.

질문은 저자가 썼다. 다만 **무엇이 정답인지는 저자의 감이 아니라 데이터로 정해지게** 했다.

  attribute / usage : 정답 = 능력치·태그 필드에 대한 규칙(rule)의 결과. 규칙이 코드로 남는다.
  visual            : 정답 = 원작자 아이콘 이름이 그 시각 특징을 담은 아이템.
                      아이템의 이름·설명·태그에는 그 특징이 없다(아래 assert 로 검증).
                      → 이미지 정보가 실제로 검색에 기여하는지 보는 질문군이다.
  lore              : 정답 = 설명문의 해당 아이템. 질문은 설명문의 핵심 단어를 피해서 바꿔 썼다.
  cross             : 정답 = 퀘스트와 그 퀘스트가 주거나 요구하는 아이템(데이터의 rewards/objectives).
  negative          : 데이터에 답이 없다. 검색 지표에는 넣지 않고 답변 단계("모른다")에서 쓴다.

한계: 질문 작성자가 문서 내용을 알고 있다. 바꿔 쓰기로 어휘 겹침을 줄였지만 0은 아니며,
이는 키워드 검색(BM25)에 유리한 방향의 편향이다. 결과는 질문 유형별로 나눠 보고한다.

사용:
    python src/build_golden.py
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DATA, EVAL, items, quests, save_jsonl  # noqa: E402

EQUIP = {"weapon", "armor", "accessory"}


def has(stat):            # 능력치가 있고 0보다 크다
    return lambda it: it["stats"].get(stat, 0) > 0


RULES = [
    # (query, type, rule, note)
    ("불에 잘 버티는 방패 추천해줘", "attribute",
     lambda it: it["subcategory"] == "shield" and has("fire_resist")(it), "shield ∧ fire_resist"),
    ("추운 데서 입을 만한 옷이나 갑옷", "attribute",
     lambda it: it["subcategory"] == "body" and has("ice_resist")(it), "body ∧ ice_resist"),
    ("독에 강해지는 장비가 뭐가 있지", "attribute",
     lambda it: it["category"] in EQUIP and has("poison_resist")(it), "equip ∧ poison_resist"),
    ("치명타가 잘 터지는 단검", "attribute",
     lambda it: it["subcategory"] == "dagger" and has("crit_rate")(it), "dagger ∧ crit_rate"),
    ("죽은 것들 상대로 잘 통하는 무기", "attribute",
     lambda it: it["category"] == "weapon" and has("undead_damage")(it), "weapon ∧ undead_damage"),
    ("번개를 쓰는 무기", "attribute",
     lambda it: it["category"] == "weapon" and has("lightning_damage")(it), "weapon ∧ lightning_damage"),
    ("공허에 버티게 해주는 것들", "attribute", has("void_resist"), "void_resist"),
    ("빨리 달리게 해주는 신발", "attribute",
     lambda it: it["subcategory"] == "boots" and has("move_speed")(it), "boots ∧ move_speed"),
    ("두 손으로 들어야 하는 무거운 무기", "attribute",
     lambda it: it["category"] == "weapon" and "양손" in it["tags"], "weapon ∧ tag 양손"),
    ("체력 채워주는 물약 종류", "usage",
     lambda it: it["subcategory"] == "potion" and has("heal")(it), "potion ∧ heal"),
    ("마나 떨어졌을 때 먹거나 마실 것", "usage",
     lambda it: it["category"] == "consumable" and has("mana_restore")(it), "consumable ∧ mana_restore"),
    ("갱도에 들고 들어갈 조명", "usage",
     lambda it: it["category"] == "tool" and has("light")(it), "tool ∧ light"),
    ("발소리 안 나게 다니고 싶은데", "usage", has("stealth"), "stealth"),
    ("잠긴 문 여는 데 도움 되는 것", "usage", has("lockpick"), "lockpick"),
    ("절벽 오를 때 도움 되는 것 전부", "usage", has("climb"), "climb"),
    ("쓰러진 동료 다시 일으키는 방법", "usage", has("revive"), "revive"),
    ("마을로 한 번에 돌아가는 방법", "usage", has("teleport"), "teleport"),
    ("물속에서 숨 쉬려면", "usage", has("water_breathing"), "water_breathing"),
    ("광석 캐려면 뭐가 필요해", "usage", has("mining"), "mining"),
    ("물고기 잡을 때 쓰는 도구", "usage", has("fishing"), "fishing"),
]

# visual: (query, [item_id], 아이콘 이름에 있어야 할 단어, 아이템 텍스트에 없어야 할 한국어 단어들)
VISUAL = [
    ("해골이 달린 지팡이", ["itm_w037"], "skull", ["해골"]),
    ("눈 모양 문양이 그려진 방패", ["itm_a007"], "eye", ["눈"]),
    ("십자가가 그려진 방패", ["itm_a006"], "templar", ["십자"]),
    ("뱀이 감겨 있는 지팡이", ["itm_w039"], "asclepius", ["뱀"]),
    ("하트 모양 병", ["itm_p002", "itm_p011"], None, ["하트"]),
    ("초승달 장식이 달린 지팡이", ["itm_w035"], "lunar", ["초승달", "달"]),
    ("날개 달린 홀", ["itm_w036"], "winged", ["날개"]),
    ("사람 모양 과자", ["itm_f005"], "gingerbread", ["사람"]),
    ("눈송이가 그려진 병", ["itm_p008"], "snow", ["눈송이"]),
    ("끝에 구슬이 달린 지팡이", ["itm_w040"], "orb", ["구슬"]),
    ("사슬이 달린 작살", ["itm_w032"], "chain", ["사슬"]),
    ("고사리처럼 생긴 풀", ["itm_m014"], "fern", ["고사리"]),
]

LORE = [
    ("죽은 선장이 남기고 간 검", ["itm_w006"]),
    ("두 동강 난 채로 발견됐다는 전설의 검", ["itm_w012"]),
    ("한 사람만 지키겠다는 서약이 걸린 검", ["itm_w011"]),
    ("마법 학교에서 들고 들어오지 못하게 막은 지팡이", ["itm_w037"]),
    ("짝이 곁에 있어야만 힘을 내는 반지", ["itm_c006"]),
    ("사냥꾼들이 첫 사냥감으로 만들어 거는 장신구", ["itm_c007"]),
    ("남들이 내 이름을 잊게 되는 물건", ["itm_c015"]),
    ("밤에만 익고 아침이면 말라버리는 열매", ["itm_f007"]),
    ("팔지도 버리지도 못해서 가방만 차지하는 열쇠", ["itm_t015"]),
    ("성당에서 그냥 나눠주는 부적", ["itm_c012"]),
]

CROSS = [
    ("불티검 엠버는 어떤 의뢰를 해야 얻어", ["qst_020", "itm_w005"]),
    ("잠수부 투구가 있어야 깰 수 있는 퀘스트", ["qst_027", "itm_a012"]),
    ("허공을 딛는 장화가 필요한 퀘스트", ["qst_035", "itm_a035"]),
    ("늪거북 잡아서 방패 만들어 주는 의뢰", ["qst_012", "itm_a003"]),
    ("봉인 해제 주문서는 누가 줘", ["qst_034", "itm_s006"]),
    ("폭풍을 부르는 홀은 어떻게 얻어", ["qst_032", "itm_w040"]),
    ("강철 곡괭이를 가져가야 하는 의뢰", ["qst_019", "itm_t004"]),
    ("반딧불 잡아 달라는 의뢰와 그 보상", ["qst_013", "itm_c008"]),
]

NEGATIVE = [
    "총이나 화약 무기는 어디서 구해",
    "타고 다닐 말이나 탈것 파는 곳",
    "펫한테 먹이는 사료",
    "레벨 70 넘어야 쓰는 장비",
    "결혼식 올릴 때 필요한 아이템",
    "하늘을 날게 해주는 물약",
]


def main() -> None:
    its = items()
    by_id = {it["id"]: it for it in its}
    qids = {q["id"] for q in quests()}
    with open(DATA / "icon_map.csv", encoding="utf-8", newline="") as f:
        icon_name = {r["item_id"]: r["icon_name"] for r in csv.DictReader(f)}

    rows = []

    def add(query, qtype, ids, note):
        for i in ids:
            assert i in by_id or i in qids, "없는 id: %s" % i
        rows.append({"qid": "q%03d" % (len(rows) + 1), "query": query, "relevant_ids": sorted(ids),
                     "query_type": qtype, "note": note})

    for query, qtype, rule, note in RULES:
        ids = [it["id"] for it in its if rule(it)]
        assert ids, "규칙에 걸리는 아이템이 없다: %s" % query
        add(query, qtype, ids, "rule: " + note)

    for query, ids, must, absent in VISUAL:
        for i in ids:
            it = by_id[i]
            text = it["name"] + it["description"] + "".join(it["tags"])
            leaked = [w for w in absent if w in text]
            assert not leaked, "%s: 시각 단어 %s 가 아이템 텍스트에 이미 있다" % (i, leaked)
        if must:
            assert all(must in icon_name[i] for i in ids), "%s: 아이콘 이름에 '%s' 없음" % (ids, must)
        add(query, "visual", ids, "icon: " + ", ".join(icon_name[i] for i in ids))

    for query, ids in LORE:
        add(query, "lore", ids, "설명문 바꿔 쓰기")
    for query, ids in CROSS:
        add(query, "cross", ids, "퀘스트 rewards/objectives")
    for query in NEGATIVE:
        add(query, "negative", [], "데이터에 답 없음 — 검색 지표 제외, 답변 단계용")

    save_jsonl(EVAL / "golden_queries.jsonl", rows)
    from collections import Counter
    print("질문 %d개: %s" % (len(rows), dict(Counter(r["query_type"] for r in rows))))
    multi = sum(1 for r in rows if len(r["relevant_ids"]) > 1)
    print("정답이 2개 이상인 질문 %d개 · 최대 %d개" % (multi, max(len(r["relevant_ids"]) for r in rows)))


if __name__ == "__main__":
    main()
