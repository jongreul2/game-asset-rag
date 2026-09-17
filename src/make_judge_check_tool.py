# -*- coding: utf-8 -*-
"""LLM 판정관 검증 도구(tools/judge_check.html)를 만든다.

판정관이 내린 판정 중 30건을 뽑아 **사람이 같은 3단계로 따로 채점**한다.
사람은 판정관의 판정을 보지 못한다(블라인드). 둘의 일치율이 판정관의 신뢰도다.

표본은 판정별로 층화한다(match 12 · partial 9 · miss 9). 무작위로만 뽑으면 대부분
match 라서 partial/miss 구간에서 판정관이 맞는지 확인할 수 없다.

사용:
    python src/make_judge_check_tool.py
    (채점 후 내려받은 judge_check.json 을 eval/ 에 둔다)
"""
from __future__ import annotations

import csv
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DATA, ROOT  # noqa: E402
from judge_labels import load_verdicts  # noqa: E402

SEED = 20260917
QUOTA = {"match": 12, "partial": 9, "miss": 9}

HTML = """<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8"><title>판정관 검증</title>
<style>
  body { margin:0; font-family:"Malgun Gothic",system-ui,sans-serif; background:#fafafa; color:#1a1a1a;
         display:flex; justify-content:center; padding:32px 16px; }
  .wrap { width:100%; max-width:560px; }
  .bar { height:6px; background:#e0e0e0; border-radius:3px; overflow:hidden; margin-bottom:8px; }
  .bar > div { height:100%; background:#2f6fed; width:0%; transition:width .2s; }
  .meta { font-size:13px; color:#6b6b6b; margin-bottom:20px; display:flex; justify-content:space-between; }
  .card { background:#fff; border:1px solid #e0e0e0; border-radius:12px; padding:24px; text-align:center; }
  img { width:200px; height:200px; object-fit:contain; }
  .name { font-size:13px; color:#6b6b6b; margin-top:4px; }
  .ans { font-size:22px; font-weight:700; margin:18px 0 6px; }
  .q { font-size:14px; color:#6b6b6b; }
  .row { display:flex; gap:8px; margin-top:20px; }
  button { flex:1; padding:14px 8px; font-size:15px; font-family:inherit; border:1px solid #e0e0e0;
           background:#fff; border-radius:8px; cursor:pointer; line-height:1.5; }
  button small { display:block; color:#6b6b6b; font-size:12px; }
  .m { background:#e8f5e9; border-color:#a5d6a7; } .p { background:#fff8e1; border-color:#ffe082; }
  .x { background:#fdecea; border-color:#f5b7b1; } .sel { outline:3px solid #2f6fed; }
  .nav button { font-size:13px; padding:8px; color:#6b6b6b; margin-top:8px; }
  .done { margin-top:24px; padding:20px; background:#fff; border:1px solid #e0e0e0; border-radius:12px; font-size:14px; line-height:1.7; }
  .done button { background:#2f6fed; color:#fff; border-color:#2f6fed; font-weight:600; margin-top:8px; width:100%; }
  code { background:#f0f0f0; padding:2px 6px; border-radius:4px; font-size:13px; }
  .note { font-size:13px; color:#6b6b6b; line-height:1.7; margin-top:20px; }
</style></head><body><div class="wrap">
  <div class="bar"><div id="prog"></div></div>
  <div class="meta"><span id="count"></span><span id="judged"></span></div>
  <div class="card">
    <img id="icon" alt="">
    <div class="name">작가가 붙인 이름: <b id="name"></b></div>
    <div class="q" style="margin-top:16px">누군가 이 그림을 보고 이렇게 적었습니다</div>
    <div class="ans" id="ans"></div>
    <div class="row">
      <button class="m" id="b1">맞다<small>같은 물건 · 키 1</small></button>
      <button class="p" id="b2">비슷하지만 다른 물건<small>예: 단검→검 · 키 2</small></button>
      <button class="x" id="b3">틀리다<small>다른 물건/모르겠음 · 키 3</small></button>
    </div>
    <div class="nav"><button id="prev">← 이전으로</button></div>
  </div>
  <div class="done">다 하면 파일을 받아 <code>game-asset-rag\\eval\\</code> 에 넣으세요.
    <button id="download">judge_check.json 내려받기</button></div>
  <p class="note">
    <b>맞다</b>: 표현이 달라도 같은 물건(신발↔부츠, 포션↔물약병). 더 자세하거나 조금 더 일반적인 말도 포함.<br>
    <b>비슷하지만 다른 물건</b>: 큰 분류는 같은데 물건이 다름(반지↔팔찌, 투구↔갑옷).<br>
    <b>틀리다</b>: 아예 다른 물건이거나 "모르겠음".<br>
    누가 쓴 답인지, AI 판정관이 어떻게 판정했는지는 일부러 가렸습니다.
  </p>
</div>
<script>
const PAIRS = __PAIRS__;
const KEY = "judge_check_v1";
let store = JSON.parse(localStorage.getItem(KEY) || "{}");
let i = 0;
const $ = id => document.getElementById(id);
const V = ["match", "partial", "miss"];
function render() {
  const p = PAIRS[i];
  $("icon").src = "../data/icons/" + p.icon;
  $("name").textContent = p.icon_name; $("ans").textContent = p.answer;
  $("count").textContent = (i + 1) + " / " + PAIRS.length;
  const n = PAIRS.filter(q => store[q.key]).length;
  $("judged").textContent = "채점 " + n + "건";
  $("prog").style.width = (100 * n / PAIRS.length) + "%";
  ["b1", "b2", "b3"].forEach((b, j) => $(b).classList.toggle("sel", store[p.key] === V[j]));
  $("prev").disabled = i === 0;
}
function judge(v) {
  store[PAIRS[i].key] = v; localStorage.setItem(KEY, JSON.stringify(store));
  if (i < PAIRS.length - 1) i++; render();
}
$("b1").onclick = () => judge("match"); $("b2").onclick = () => judge("partial"); $("b3").onclick = () => judge("miss");
$("prev").onclick = () => { if (i > 0) { i--; render(); } };
document.addEventListener("keydown", e => { if (["1", "2", "3"].includes(e.key)) judge(V[+e.key - 1]); });
$("download").onclick = () => {
  const out = {}; PAIRS.forEach(p => { if (store[p.key]) out[p.key] = store[p.key]; });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([JSON.stringify(out, null, 1)], {type: "application/json"}));
  a.download = "judge_check.json"; a.click();
};
render();
</script></body></html>
"""


def main() -> None:
    verdicts = load_verdicts()
    with open(DATA / "icon_map.csv", encoding="utf-8", newline="") as f:
        icon_file = {r["icon_name"]: r["icon_file"] for r in csv.DictReader(f)}

    rng = random.Random(SEED)
    picked = []
    for verdict, n in QUOTA.items():
        pool = sorted(k for k, v in verdicts.items() if v["verdict"] == verdict and v["icon_name"] in icon_file)
        picked += rng.sample(pool, min(n, len(pool)))
    rng.shuffle(picked)
    pairs = [{"key": k, "icon": icon_file[verdicts[k]["icon_name"]],
              "icon_name": verdicts[k]["icon_name"], "answer": verdicts[k]["answer"]} for k in picked]

    out = ROOT / "tools" / "judge_check.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(HTML.replace("__PAIRS__", json.dumps(pairs, ensure_ascii=False)), encoding="utf-8")
    print("작성: tools/judge_check.html — %d건 (판정별 층화, 판정 결과는 가림)" % len(pairs))


if __name__ == "__main__":
    main()
