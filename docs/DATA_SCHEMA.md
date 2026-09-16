# 데이터 스키마

전부 이 저장소를 위해 창작한 가상 데이터다. 실제 상용 게임 IP·데이터는 쓰지 않았다.
세계관: 2D 판타지 MMO "에버셰이드 연대기"(가상). 지역 = 실버브룩 · 잿빛습지 · 붉은협곡 · 서리항구 · 공허탑.

## `data/items.jsonl` — 아이템

| 필드 | 타입 | 설명 |
|---|---|---|
| `id` | str | `itm_<분류약어><번호>` (예: `itm_w001`) |
| `name` | str | 아이템 이름 |
| `category` | str | `weapon` · `armor` · `accessory` · `consumable` · `material` · `tool` |
| `subcategory` | str | `sword` · `shield` · `potion` 등 |
| `rarity` | str | `common` · `uncommon` · `rare` · `epic` · `legendary` |
| `level_req` | int | 착용/사용 요구 레벨 |
| `price` | int | 상점가(골드) |
| `stats` | obj | 수치. 없으면 `{}` |
| `description` | str | 인게임 설명문. **실제 게임처럼 플레이버 위주로 쓴다 — 외형을 일부러 설명하거나 일부러 감추지 않는다** |
| `tags` | list | 검색 보조 태그 |
| `region` | str | 주 획득 지역 |
| `icon` | str/null | `data/icons/` 내 파일명. 매핑 단계에서 채움 |
| `icon_author` | str/null | game-icons.net 원작자 (CC BY 3.0 표기용) |

> ⚠ **설명문 작성 원칙**: 조건 B(자동 라벨 결합)·D(이미지 임베딩)가 유리해지도록 외형 정보를 의도적으로 빼지 않는다. 실제 게임 설명문의 분포를 따라 쓰고, 이미지가 실제로 정보를 더하는지는 평가가 답하게 한다.

## `data/quests.jsonl` — 퀘스트

| 필드 | 타입 | 설명 |
|---|---|---|
| `id` | str | `qst_<번호>` |
| `title` | str | 퀘스트 이름 |
| `giver` | str | 의뢰 NPC |
| `level_req` | int | 수락 요구 레벨 |
| `region` | str | 수행 지역 |
| `summary` | str | 퀘스트 설명문 |
| `objectives` | list | 목표 문자열 |
| `rewards` | list | 보상(아이템 id 또는 문자열) |
| `tags` | list | 검색 보조 태그 |

## `eval/golden_queries.jsonl` — 검색 정답셋

| 필드 | 타입 | 설명 |
|---|---|---|
| `qid` | str | `q001` |
| `query` | str | 플레이어가 NPC에게 던지는 자연어 질문 |
| `relevant_ids` | list | 정답 문서 id (순서 무관, 1개 이상) |
| `query_type` | str | `attribute`(속성) · `usage`(용도) · `lore`(설정) · `cross`(아이템↔퀘스트 교차) · `negative`(데이터에 답이 없음) |
| `note` | str | 정답 판정 근거 |

> `negative` 질문은 "모른다"를 제대로 말하는지 보기 위한 것이라 `relevant_ids`가 빈 배열이다.

## `data/label_gold.jsonl` — 라벨 정답 (사람 작성 50건)

| 필드 | 타입 | 설명 |
|---|---|---|
| `item_id` | str | 대상 아이템 |
| `shape` | str | 아이콘에서 보이는 형태 |
| `object_kind` | str | 무엇을 그린 것인지 |
| `visual_tags` | list | 아이콘에서 읽히는 속성 |
