# -*- coding: utf-8 -*-
"""검색 평가 — "아이콘에서 뽑은 정보를 더하면 검색이 좋아지는가"를 같은 정답셋으로 잰다.

문서 구성(무엇을 색인하는가)
  A  텍스트만            이름·분류·설명·태그·지역·능력치(한국어로 풀어 씀)
  B  텍스트 + 자동 라벨   A 에 비전 LLM 이 아이콘만 보고 만든 라벨을 덧붙임 (Sonnet 5 / Haiku 4.5 각각)
  D  텍스트 + 이미지      A 의 텍스트와 아이콘 PNG 를 멀티모달 임베딩 하나로 (라벨링 단계 없음)
검색기(어떻게 찾는가)
  dense   임베딩 코사인 (voyage-4 / D 는 voyage-multimodal-3.5)
  bm25    키워드. 형태소 분석기 없이 어절 + 문자 바이그램 토큰
  hybrid  dense 와 bm25 순위를 RRF(k=60)로 결합   ← 계획서의 '조건 C'

퀘스트 문서에는 아이콘이 없으므로 B·D 에서도 텍스트만 들어간다.
임베딩은 data/cache/ 에 저장해 다시 돌릴 때 API 를 부르지 않는다.

사용:
    python src/search_eval.py
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DATA, EVAL, RESULTS, items, load_jsonl, quests, require_key  # noqa: E402

TEXT_MODEL = "voyage-4"
MM_MODEL = "voyage-multimodal-3.5"
CACHE = DATA / "cache"
K = 5
RRF_K = 60

CATEGORY_KO = {"weapon": "무기", "armor": "방어구", "accessory": "장신구",
               "consumable": "소비품", "material": "재료", "tool": "도구"}
STAT_KO = {
    "attack": "공격력", "magic_attack": "마법 공격력", "defense": "방어력", "hp": "체력", "mana": "마나",
    "fire_damage": "화염 피해", "ice_damage": "냉기 피해", "lightning_damage": "번개 피해",
    "poison_damage": "독 피해", "holy_damage": "신성 피해", "void_damage": "공허 피해",
    "undead_damage": "언데드 추가 피해", "fire_resist": "화염 저항", "ice_resist": "냉기 저항",
    "poison_resist": "독 저항", "void_resist": "공허 저항", "undead_resist": "언데드 저항",
    "all_resist": "모든 저항", "burn_resist": "화상 저항", "silence_resist": "침묵 저항",
    "crit_rate": "치명타 확률", "attack_speed": "공격 속도", "move_speed": "이동 속도", "range": "사거리",
    "lifesteal": "생명력 흡수", "mana_steal": "마나 흡수", "mana_regen": "마나 재생",
    "stun_chance": "기절 확률", "backstab_damage": "배후 공격 피해", "execute_threshold": "처형 기준 체력",
    "heal": "체력 회복", "heal_power": "치유량", "heal_over_time": "지속 회복", "mana_restore": "마나 회복",
    "stamina": "지구력", "light": "조명", "stealth": "은신", "lockpick": "자물쇠 따기", "climb": "등반",
    "mining": "채광", "fishing": "낚시", "herbalism": "약초 채집", "navigation": "항해·길찾기",
    "revive": "부활", "teleport": "순간이동", "water_breathing": "수중 호흡", "invisible": "투명화",
    "shield": "보호막", "identify": "감정", "unseal": "봉인 해제", "luck": "행운", "reflect": "반사",
    "swamp_move": "늪지 이동", "air_jump": "공중 도약", "pull_effect": "끌어당김", "grapple": "갈고리 걸기",
    "ice_drill": "얼음 뚫기", "rest": "휴식", "trap_damage": "덫 피해", "root": "속박", "intimidate": "위압",
    "all_stat": "모든 능력치", "party_bonus": "파티 보너스", "accuracy": "명중", "duration": "지속시간(초)",
    "cure_poison": "해독", "identity": "정체 은폐",
}


# ---------- 문서 ----------
def item_text(it: dict) -> str:
    stats = ", ".join("%s %s" % (STAT_KO.get(k, k), v) for k, v in it["stats"].items())
    return "\n".join(filter(None, [
        "%s (%s · %s · 요구 레벨 %d)" % (it["name"], CATEGORY_KO[it["category"]], it["rarity"], it["level_req"]),
        it["description"],
        "능력치: " + stats if stats else "",
        "태그: " + ", ".join(it["tags"]),
        "획득 지역: " + it["region"],
    ]))


def quest_text(q: dict, names: dict[str, str]) -> str:
    rewards = ", ".join(names.get(r, r) for r in q["rewards"])
    return "\n".join([
        "퀘스트: %s (의뢰인 %s · %s · 요구 레벨 %d)" % (q["title"], q["giver"], q["region"], q["level_req"]),
        q["summary"], "목표: " + " / ".join(q["objectives"]), "보상: " + rewards, "태그: " + ", ".join(q["tags"]),
    ])


def label_text(lb: dict) -> str:
    return ("[아이콘에서 읽은 정보] %s. 형태: %s. 구성: %s. 쓰임새: %s. 시각 태그: %s. %s"
            % (lb["object_kind"], lb["shape"], ", ".join(lb["components"]), lb["likely_use"],
               ", ".join(lb["tags"]), lb["one_line"]))


def build_corpora():
    its, qs = items(), quests()
    names = {it["id"]: it["name"] for it in its}
    ids = [it["id"] for it in its] + [q["id"] for q in qs]
    base = {it["id"]: item_text(it) for it in its}
    base.update({q["id"]: quest_text(q, names) for q in qs})
    corp = {"A": base}
    for m in ("sonnet-5", "haiku-4-5"):
        labels = {r["item_id"]: r["label"] for r in load_jsonl(RESULTS / ("labels_%s.jsonl" % m))}
        corp["B:" + m] = {i: base[i] + ("\n" + label_text(labels[i]) if i in labels else "") for i in ids}
    icons = {it["id"]: it["icon"] for it in its}
    return ids, corp, icons


# ---------- 임베딩(캐시 + 재시도) ----------
def _key(*parts: str) -> str:
    return hashlib.sha1("\x1f".join(parts).encode("utf-8")).hexdigest()


class Embedder:
    def __init__(self):
        require_key("VOYAGE_API_KEY")
        import voyageai
        self.vo = voyageai.Client()
        self.err = voyageai.error
        self.tokens = defaultdict(int)
        self._last = 0.0
        CACHE.mkdir(parents=True, exist_ok=True)

    def _load(self, name):
        p = CACHE / (name + ".json")
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}

    def _save(self, name, cache):
        (CACHE / (name + ".json")).write_text(json.dumps(cache), encoding="utf-8")

    def _call(self, fn, **kw):
        # 결제수단을 등록하지 않은 Voyage 계정은 분당 요청·토큰 한도가 매우 낮다(3 RPM 수준).
        # 429 를 맞고 물러서는 대신 요청 간격을 미리 벌린다. 한도가 넉넉한 계정은
        # VOYAGE_MIN_INTERVAL=0 으로 끄면 된다.
        gap = float(os.environ.get("VOYAGE_MIN_INTERVAL", "21"))
        for attempt in range(8):
            wait = gap - (time.time() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.time()
            try:
                return fn(**kw)
            except self.err.RateLimitError as e:
                if attempt == 0:
                    print("    (요청 한도: %s)" % str(e)[:160])
                time.sleep(30)
        raise SystemExit("Voyage 요청 한도를 넘지 못했다. 묶음 크기(chunk)를 더 줄여라.")

    def text(self, texts: list[str], input_type: str, chunk: int = 16) -> np.ndarray:
        name = "%s_%s" % (TEXT_MODEL, input_type)
        cache = self._load(name)
        todo = [t for t in dict.fromkeys(texts) if _key(t) not in cache]
        for s in range(0, len(todo), chunk):
            part = todo[s:s + chunk]
            r = self._call(self.vo.embed, texts=part, model=TEXT_MODEL, input_type=input_type)
            self.tokens[TEXT_MODEL] += r.total_tokens
            for t, e in zip(part, r.embeddings):
                cache[_key(t)] = e
            self._save(name, cache)
            print("    %s %s: %d / %d" % (TEXT_MODEL, input_type, min(s + chunk, len(todo)), len(todo)))
        return _norm(np.array([cache[_key(t)] for t in texts]))

    def multimodal(self, docs: list[tuple[str, str | None]], input_type: str, chunk: int = 4) -> np.ndarray:
        """docs: (텍스트, 아이콘 파일명 또는 None)"""
        from PIL import Image
        name = "%s_%s" % (MM_MODEL, input_type)
        cache = self._load(name)
        todo = [d for d in dict.fromkeys(docs) if _key(d[0], d[1] or "") not in cache]
        for s in range(0, len(todo), chunk):
            part = todo[s:s + chunk]
            inputs = [[t] + ([Image.open(DATA / "icons" / ic).convert("RGB")] if ic else []) for t, ic in part]
            r = self._call(self.vo.multimodal_embed, inputs=inputs, model=MM_MODEL, input_type=input_type)
            self.tokens[MM_MODEL] += r.total_tokens
            for d, e in zip(part, r.embeddings):
                cache[_key(d[0], d[1] or "")] = e
            self._save(name, cache)
            print("    %s %s: %d / %d" % (MM_MODEL, input_type, min(s + chunk, len(todo)), len(todo)))
        return _norm(np.array([cache[_key(t, ic or "")] for t, ic in docs]))


def _norm(m: np.ndarray) -> np.ndarray:
    return m / np.linalg.norm(m, axis=1, keepdims=True)


# ---------- 검색기 ----------
def tokenize(s: str) -> list[str]:
    """형태소 분석기 없이 한국어 BM25: 어절 + 어절 안의 문자 바이그램."""
    toks = []
    for w in s.replace("\n", " ").split():
        w = "".join(ch for ch in w if ch.isalnum())
        if not w:
            continue
        toks.append(w)
        toks += [w[i:i + 2] for i in range(len(w) - 1)]
    return toks


def rank_dense(doc_emb: np.ndarray, q_emb: np.ndarray) -> np.ndarray:
    return np.argsort(-(q_emb @ doc_emb.T), axis=1)


def rank_bm25(doc_texts: list[str], queries: list[str]) -> np.ndarray:
    from rank_bm25 import BM25Okapi
    bm = BM25Okapi([tokenize(t) for t in doc_texts])
    return np.array([np.argsort(-bm.get_scores(tokenize(q))) for q in queries])


def rrf(*rankings: np.ndarray) -> np.ndarray:
    n_q, n_d = rankings[0].shape
    score = np.zeros((n_q, n_d))
    for r in rankings:
        for q in range(n_q):
            score[q, r[q]] += 1.0 / (RRF_K + np.arange(1, n_d + 1))
    return np.argsort(-score, axis=1)


# ---------- 지표 ----------
def evaluate(ranking: np.ndarray, ids: list[str], gold: list[dict]) -> dict:
    per_q = []
    for qi, g in enumerate(gold):
        rel = set(g["relevant_ids"])
        order = [ids[j] for j in ranking[qi]]
        first = next(r for r, d in enumerate(order, 1) if d in rel)
        hits = len(rel & set(order[:K]))
        per_q.append({"qid": g["qid"], "type": g["query_type"], "recall": hits / len(rel),
                      "rr": 1.0 / first, "hit1": float(order[0] in rel), "first_rank": first, "top": order[:K]})
    out = {"all": _agg(per_q)}
    for t in sorted({p["type"] for p in per_q}):
        out[t] = _agg([p for p in per_q if p["type"] == t])
    out["per_query"] = per_q
    return out


def _agg(rows: list[dict]) -> dict:
    return {"n": len(rows), "recall@%d" % K: float(np.mean([r["recall"] for r in rows])),
            "mrr": float(np.mean([r["rr"] for r in rows])), "hit@1": float(np.mean([r["hit1"] for r in rows]))}


def main() -> None:
    ids, corp, icons = build_corpora()
    gold = [g for g in load_jsonl(EVAL / "golden_queries.jsonl") if g["query_type"] != "negative"]
    queries = [g["query"] for g in gold]
    print("문서 %d개 · 질문 %d개" % (len(ids), len(queries)))

    emb = Embedder()
    q_text = emb.text(queries, "query")
    runs: dict[str, dict] = {}
    rank_cache: dict[str, np.ndarray] = {}
    for name, docs in corp.items():
        print("[%s]" % name)
        texts = [docs[i] for i in ids]
        dense = rank_dense(emb.text(texts, "document"), q_text)
        bm = rank_bm25(texts, queries)
        rank_cache[name + "|bm25"] = bm
        runs[name + " · dense"] = evaluate(dense, ids, gold)
        runs[name + " · bm25"] = evaluate(bm, ids, gold)
        runs[name + " · hybrid"] = evaluate(rrf(dense, bm), ids, gold)

    print("[D]")
    a_texts = [corp["A"][i] for i in ids]
    d_docs = [(corp["A"][i], icons.get(i)) for i in ids]
    dense_d = rank_dense(emb.multimodal(d_docs, "document"), emb.multimodal([(q, None) for q in queries], "query"))
    runs["D · dense"] = evaluate(dense_d, ids, gold)
    runs["D · hybrid"] = evaluate(rrf(dense_d, rank_cache["A|bm25"]), ids, gold)
    # 멀티모달 모델 자체의 영향 분리용: 같은 모델에 이미지 없이 텍스트만 넣은 대조군
    dense_d0 = rank_dense(emb.multimodal([(t, None) for t in a_texts], "document"),
                          emb.multimodal([(q, None) for q in queries], "query"))
    runs["D0(이미지 없음) · dense"] = evaluate(dense_d0, ids, gold)

    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "search_eval.json").write_text(json.dumps(
        {"k": K, "text_model": TEXT_MODEL, "mm_model": MM_MODEL, "tokens": dict(emb.tokens), "runs": runs},
        ensure_ascii=False, indent=1), encoding="utf-8")

    print("\n%-28s %9s %7s %7s" % ("조건", "recall@%d" % K, "MRR", "hit@1"))
    for name, r in runs.items():
        a = r["all"]
        print("%-28s %9.3f %7.3f %7.3f" % (name, a["recall@%d" % K], a["mrr"], a["hit@1"]))
    print("\n이번 실행에서 새로 쓴 Voyage 토큰:", dict(emb.tokens) or "0 (전부 캐시)")


if __name__ == "__main__":
    main()
