# -*- coding: utf-8 -*-
"""정답 라벨을 브라우저에서 채우는 로컬 도구(tools/label_gold.html)를 만든다.

아이콘만 크게 보여 주고 한 칸만 묻는다. **아이템 이름·설명은 화면에 띄우지 않는다** —
이름을 보면 정답이 설명문을 따라가고, 이미지만 본 모델과 비교할 수 없게 되기 때문이다.

사용:
    python src/make_gold_tool.py        # tools/label_gold.html 생성 → 브라우저로 열기
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import EVAL, ROOT, load_jsonl  # noqa: E402

HTML = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>정답 라벨 작성</title>
<style>
  :root { --fg:#1a1a1a; --muted:#6b6b6b; --line:#e0e0e0; --accent:#2f6fed; }
  * { box-sizing: border-box; }
  body { margin:0; font-family: "Malgun Gothic", system-ui, sans-serif; color:var(--fg);
         background:#fafafa; display:flex; justify-content:center; padding:32px 16px; }
  .wrap { width:100%; max-width:560px; }
  .bar { height:6px; background:var(--line); border-radius:3px; overflow:hidden; margin-bottom:8px; }
  .bar > div { height:100%; background:var(--accent); width:0%; transition:width .2s; }
  .meta { display:flex; justify-content:space-between; font-size:13px; color:var(--muted); margin-bottom:20px; }
  .card { background:#fff; border:1px solid var(--line); border-radius:12px; padding:24px; text-align:center; }
  img { width:220px; height:220px; object-fit:contain; }
  label { display:block; text-align:left; font-size:14px; margin:20px 0 6px; font-weight:600; }
  .hint { font-weight:400; color:var(--muted); font-size:13px; }
  input[type=text] { width:100%; padding:12px 14px; font-size:16px; border:1px solid var(--line);
                     border-radius:8px; font-family:inherit; }
  input[type=text]:focus { outline:2px solid var(--accent); border-color:transparent; }
  .row { display:flex; gap:8px; margin-top:16px; }
  button { flex:1; padding:12px; font-size:15px; font-family:inherit; border:1px solid var(--line);
           background:#fff; border-radius:8px; cursor:pointer; }
  button.primary { background:var(--accent); color:#fff; border-color:var(--accent); font-weight:600; }
  button:disabled { opacity:.4; cursor:default; }
  .done { margin-top:24px; padding:20px; background:#fff; border:1px solid var(--line); border-radius:12px; }
  .done p { font-size:14px; line-height:1.7; }
  code { background:#f0f0f0; padding:2px 6px; border-radius:4px; font-size:13px; }
  .note { font-size:13px; color:var(--muted); line-height:1.7; margin-top:20px; }
</style>
</head>
<body>
<div class="wrap">
  <div class="bar"><div id="prog"></div></div>
  <div class="meta"><span id="count"></span><span id="saved"></span></div>

  <div class="card">
    <img id="icon" alt="아이콘">
    <label for="kind">이 아이콘은 무엇을 그린 것인가요?
      <span class="hint">짧은 명사구로. 예: 한손 검 / 원형 방패 / 유리병 / 모르겠음</span>
    </label>
    <input type="text" id="kind" autocomplete="off" placeholder="여기에 입력하고 Enter">
    <div class="row">
      <button id="prev">← 이전</button>
      <button id="next" class="primary">다음 →</button>
    </div>
  </div>

  <div class="done">
    <p><b>다 채우면</b> 아래 버튼을 눌러 파일을 받고,
       <code>game-asset-rag\\eval\\</code> 폴더에 덮어쓰세요.</p>
    <button id="download" class="primary">__FILE__ 내려받기</button>
  </div>

  <p class="note">
    입력은 브라우저에 자동 저장됩니다. 창을 닫았다 다시 열어도 이어서 하면 됩니다.<br>
    아이템 이름과 설명은 일부러 보여주지 않습니다 — 이름을 보고 적으면 "이미지만 보고 판단한
    정답"이 아니게 되고, 모델과 같은 조건에서 비교할 수 없게 됩니다.<br>
    모르겠으면 <b>모르겠음</b> 이라고 적으세요. 그것도 데이터입니다.
  </p>
</div>

<script>
const ITEMS = __ITEMS__;
const KEY = "__KEY__";
let store = JSON.parse(localStorage.getItem(KEY) || "{}");
// 아이콘이 교체된 항목은 예전 입력을 한 번만 지운다(그림이 달라졌으므로 예전 답은 무효).
const RESET = __RESET__;
if (store.__round !== RESET.round) {
  RESET.ids.forEach(id => delete store[id]);
  store.__round = RESET.round;
  localStorage.setItem(KEY, JSON.stringify(store));
}
let i = 0;

const $ = id => document.getElementById(id);

function render() {
  const it = ITEMS[i];
  $("icon").src = "../data/icons/" + it.icon;
  $("kind").value = store[it.item_id] || "";
  $("count").textContent = (i + 1) + " / " + ITEMS.length;
  const filled = ITEMS.filter(it => store[it.item_id] && store[it.item_id].trim()).length;
  $("saved").textContent = "채운 칸 " + filled + "개";
  $("prog").style.width = (100 * filled / ITEMS.length) + "%";
  $("prev").disabled = i === 0;
  $("kind").focus();
}

function save() {
  store[ITEMS[i].item_id] = $("kind").value.trim();
  localStorage.setItem(KEY, JSON.stringify(store));
}

function go(d) { save(); i = Math.min(ITEMS.length - 1, Math.max(0, i + d)); render(); }

$("next").onclick = () => go(1);
$("prev").onclick = () => go(-1);
$("kind").addEventListener("keydown", e => { if (e.key === "Enter") go(1); });

$("download").onclick = () => {
  save();
  const lines = ITEMS.map(it => JSON.stringify({
    item_id: it.item_id,
    icon: it.icon,
    object_kind: store[it.item_id] || "",
    shape: "", components: [], material_guess: "", likely_use: "", tags: []
  }));
  const blob = new Blob([lines.join("\\n") + "\\n"], {type: "application/jsonl"});
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "__FILE__";
  a.click();
};

render();
</script>
</body>
</html>
"""


def main() -> None:
    # --only-blank: 아직 비어 있는 행만 묻는다(표본을 보충했을 때). 저장 키·파일명을 달리해
    # 이전 입력이 섞이지 않게 한다. 받은 파일은 src/merge_gold.py 로 합친다.
    only_blank = "--only-blank" in sys.argv
    rows = load_jsonl(EVAL / "label_gold.jsonl")
    if only_blank:
        rows = [r for r in rows if not r.get("object_kind", "").strip()]
    key, fname = ("gold_labels_topup_v2", "label_gold_topup.jsonl") if only_blank else ("gold_labels_v1", "label_gold.jsonl")
    payload = json.dumps([{"item_id": r["item_id"], "icon": r["icon"]} for r in rows], ensure_ascii=False)
    # --reset id1,id2 : 아이콘을 교체한 항목. 브라우저에 남은 예전 입력을 지우게 한다.
    reset_ids = []
    for a in sys.argv:
        if a.startswith("--reset="):
            reset_ids = [x for x in a.split("=", 1)[1].split(",") if x]
    reset = json.dumps({"round": ",".join(sorted(reset_ids)) or "none", "ids": reset_ids})
    out = ROOT / "tools" / "label_gold.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(HTML.replace("__ITEMS__", payload).replace("__KEY__", key).replace("__FILE__", fname)
                   .replace("__RESET__", reset),
                   encoding="utf-8")
    print("작성: tools/label_gold.html (%d건)" % len(rows))
    print("브라우저로 열어서 채운 뒤, 내려받은 파일을 eval/label_gold.jsonl 로 덮어쓰면 된다.")


if __name__ == "__main__":
    main()
