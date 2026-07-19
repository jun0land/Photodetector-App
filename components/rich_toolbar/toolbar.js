/* 리치 입력 툴바 (G4 / PLAN §8.4). 소유: WP6.
 *
 * 선택 영역을 마크업으로 감싼다 (DOM->마크업 직렬화기 없음 = 검증된 파서 무오염).
 *   선택 -> B   ⇒  **선택**
 *   선택 -> I   ⇒  *선택*
 *   선택 -> x²  ⇒  ^{선택}      (중괄호 필수 — MARKUP_HELP)
 *   선택 -> x₂  ⇒  _{선택}
 *   선택 -> 색  ⇒  {#FF0000|선택}
 *
 * V4: setStateValue 는 항상 rerun 을 유발한다 -> **키 입력마다 방출 금지.**
 *     커밋 시점은 (1) Enter (2) 포커스가 컴포넌트 밖으로 (3) 서식 버튼 누름 — 이 셋뿐.
 * V5: default() 는 data 가 바뀔 때마다 재실행된다 -> 안정 id 재사용 + property 핸들러만.
 */

const HEX_RE = /^#[0-9A-Fa-f]{6}$/;
// markup.py `_COLOR_OPEN` 과 같은 문법. $ 로 고정해 "선택 바로 앞" 만 본다.
const COLOR_TAIL = /\{(#(?:[0-9A-Fa-f]{6}|[0-9A-Fa-f]{3}))\|$/;

function starRunBefore(t, i) {
  let n = 0;
  while (i - n - 1 >= 0 && t[i - n - 1] === "*") n++;
  return n;
}

function starRunAfter(t, i) {
  let n = 0;
  while (i + n < t.length && t[i + n] === "*") n++;
  return n;
}

/* 선택 영역에 서식을 토글한다. 순수 함수 — DOM 을 건드리지 않는다(node 로 테스트됨).
 * 반환: {text, start, end}. start/end 는 "원래 선택했던 글자" 를 계속 가리켜
 * 연속 적용(위첨자 -> 색)이 그대로 이어진다.
 *
 * `*` 는 개수로 판정한다: 볼드는 양쪽 런이 2 이상일 때 해제, 이탤릭은 런이 홀수일 때 해제.
 * 덕분에 `**foo**` 에 I -> `***foo***`, `***foo***` 에 I -> `**foo**` 로 겹쳐쓰기가 성립하고
 * `**foo**` 의 볼드 마커를 이탤릭 마커로 오인해 깨뜨리지 않는다.
 */
export function wrapSelection(text, start, end, action, color) {
  text = String(text === null || text === undefined ? "" : text);
  let s = Math.max(0, Math.min(text.length, start | 0));
  let e = Math.max(0, Math.min(text.length, end | 0));
  if (s > e) {
    const t = s;
    s = e;
    e = t;
  }
  const sel = text.slice(s, e);
  const mk = (nt, ns, ne) => ({ text: nt, start: ns, end: ne });

  if (action === "bold" || action === "italic") {
    const n = action === "bold" ? 2 : 1;
    const rb = starRunBefore(text, s);
    const ra = starRunAfter(text, e);
    const off =
      action === "bold" ? rb >= 2 && ra >= 2 : rb % 2 === 1 && ra % 2 === 1;
    if (off) {
      return mk(text.slice(0, s - n) + sel + text.slice(e + n), s - n, s - n + sel.length);
    }
    const m = n === 2 ? "**" : "*";
    return mk(text.slice(0, s) + m + sel + m + text.slice(e), s + n, s + n + sel.length);
  }

  if (action === "sup" || action === "sub") {
    const pre = action === "sup" ? "^{" : "_{";
    if (s >= 2 && text.slice(s - 2, s) === pre && text.slice(e, e + 1) === "}") {
      return mk(text.slice(0, s - 2) + sel + text.slice(e + 1), s - 2, s - 2 + sel.length);
    }
    return mk(text.slice(0, s) + pre + sel + "}" + text.slice(e), s + 2, s + 2 + sel.length);
  }

  if (action === "color") {
    const hex = HEX_RE.test(color || "") ? String(color).toUpperCase() : "#FF0000";
    const m = COLOR_TAIL.exec(text.slice(0, s));
    if (m && text.slice(e, e + 1) === "}") {
      const cut = s - m[0].length;
      if (m[1].toUpperCase() === hex) {
        // 같은 색 다시 -> 토글 해제
        return mk(text.slice(0, cut) + sel + text.slice(e + 1), cut, cut + sel.length);
      }
      // 다른 색 -> 중첩하지 않고 색코드만 교체 ({#00F|{#F00|x}} 방지)
      const open = "{" + hex + "|";
      return mk(
        text.slice(0, cut) + open + sel + "}" + text.slice(e),
        cut + open.length,
        cut + open.length + sel.length
      );
    }
    const open = "{" + hex + "|";
    return mk(
      text.slice(0, s) + open + sel + "}" + text.slice(e),
      s + open.length,
      s + open.length + sel.length
    );
  }

  return mk(text, s, e);
}

const BUTTONS = [
  { action: "bold", label: "B", title: "굵게  (Ctrl+B)", cls: "pd-rt-b" },
  { action: "italic", label: "I", title: "기울임  (Ctrl+I)", cls: "pd-rt-i" },
  { action: "sup", label: "x²", title: "위첨자  ^{ }", cls: "" },
  { action: "sub", label: "x₂", title: "아래첨자  _{ }", cls: "" },
];

function build(parentElement) {
  const root = document.createElement("div");
  root.id = "pd-rt-root";
  root.className = "pd-rt";

  const bar = document.createElement("div");
  bar.className = "pd-rt-bar";
  bar.id = "pd-rt-bar";

  for (const b of BUTTONS) {
    const el = document.createElement("button");
    el.type = "button";
    el.className = "pd-rt-btn " + b.cls;
    el.dataset.action = b.action;
    el.textContent = b.label;
    el.title = b.title;
    bar.appendChild(el);
  }

  const sep = document.createElement("span");
  sep.className = "pd-rt-sep";
  bar.appendChild(sep);

  const colorBtn = document.createElement("button");
  colorBtn.type = "button";
  colorBtn.className = "pd-rt-btn pd-rt-a";
  colorBtn.id = "pd-rt-apply-color";
  colorBtn.dataset.action = "color";
  colorBtn.textContent = "A";
  colorBtn.title = "선택 영역에 이 색 적용  {#RRGGBB| }";
  bar.appendChild(colorBtn);

  const swatch = document.createElement("input");
  swatch.type = "color";
  swatch.id = "pd-rt-color";
  swatch.className = "pd-rt-swatch";
  swatch.title = "글자 색 고르기";
  bar.appendChild(swatch);

  const inp = document.createElement("input");
  inp.type = "text";
  inp.id = "pd-rt-input";
  inp.className = "pd-rt-input";
  inp.spellcheck = false;
  inp.autocomplete = "off";

  root.appendChild(bar);
  root.appendChild(inp);
  parentElement.appendChild(root);
  return root;
}

export default function (component) {
  const { data, parentElement, setStateValue } = component;
  const d = data || {};
  const value = String(d.value === null || d.value === undefined ? "" : d.value);

  // V5-1: 안정 id 로 재사용. 맹목적 append 금지 (오버레이 중첩 누수의 원인).
  let root = parentElement.querySelector("#pd-rt-root");
  if (!root) root = build(parentElement);

  const inp = root.querySelector("#pd-rt-input");
  const swatch = root.querySelector("#pd-rt-color");
  const bar = root.querySelector("#pd-rt-bar");

  inp.placeholder = String(d.placeholder || "");
  inp.setAttribute("aria-label", String(d.label || "markup"));
  if (d.color && HEX_RE.test(String(d.color))) swatch.value = String(d.color);
  else if (!swatch.value) swatch.value = "#FF0000";

  // ---- 파이썬 값 채택 ---------------------------------------------------
  // data.value 가 "지난번에 본 파이썬 값" 과 다를 때만 DOM 에 반영한다.
  // 무관한 rerun(다른 위젯) 에서 default() 가 재실행돼도 커밋 안 한 타이핑을 덮지 않는다.
  if (root.dataset.pdData !== value) {
    root.dataset.pdData = value;
    if (inp.value !== value) inp.value = value;
    const stashed = root.dataset.pdSel;
    if (stashed) {
      // 우리가 커밋해서 돌아온 왕복 -> 선택 영역을 복원해 연속 적용이 이어지게 한다
      delete root.dataset.pdSel;
      const parts = stashed.split(",");
      try {
        inp.focus();
        inp.setSelectionRange(Number(parts[0]), Number(parts[1]));
      } catch (_) {
        /* 필드가 이미 사라졌으면 무시 */
      }
    }
  }

  // ---- 커밋 ------------------------------------------------------------
  // V4: 방출 = rerun. 동등 래치로 값이 실제로 바뀐 경우에만 방출한다
  // (편집 없이 지나가는 focusout 은 rerun 을 유발하지 않는다).
  const commit = () => {
    if (inp.value === root.dataset.pdData) return;
    root.dataset.pdSel = inp.selectionStart + "," + inp.selectionEnd;
    setStateValue("value", inp.value);
  };

  const apply = (action) => {
    const r = wrapSelection(inp.value, inp.selectionStart, inp.selectionEnd, action, swatch.value);
    inp.value = r.text;
    inp.focus();
    try {
      inp.setSelectionRange(r.start, r.end);
    } catch (_) {
      /* noop */
    }
    commit();
  };

  // V5-2: property 핸들러만. addEventListener 는 재실행마다 쌓인다.
  for (const el of bar.querySelectorAll("button")) {
    // mousedown 을 먹어서 입력칸이 포커스를 잃지 않게 한다.
    // (포커스가 나가면 focusout 커밋이 먼저 터져 선택이 날아간다)
    el.onmousedown = (ev) => ev.preventDefault();
    el.onclick = () => apply(el.dataset.action);
  }

  // 색상 피커는 preventDefault 불가(네이티브 창) -> 포커스가 swatch 로 간다.
  // 하지만 swatch 는 root 안이라 focusout 커밋이 걸리지 않는다.
  // input 이벤트는 드래그 중 연속 발화 -> change(피커 닫을 때 1회) 만 사용.
  swatch.onchange = () => apply("color");

  inp.onkeydown = (ev) => {
    if (ev.key === "Enter") {
      ev.preventDefault();
      commit();
      return;
    }
    if ((ev.ctrlKey || ev.metaKey) && !ev.altKey) {
      const k = ev.key.toLowerCase();
      if (k === "b") {
        ev.preventDefault();
        apply("bold");
      } else if (k === "i") {
        ev.preventDefault();
        apply("italic");
      }
    }
  };

  // 포커스가 컴포넌트 밖으로 나갈 때만 커밋 (툴바 버튼/피커로 이동은 커밋 아님).
  root.onfocusout = (ev) => {
    if (!root.contains(ev.relatedTarget)) commit();
  };

  // V5-4: unmount 용 cleanup. (data 변경 시에는 호출되지 않는다)
  return () => {
    root.onfocusout = null;
    inp.onkeydown = null;
    swatch.onchange = null;
    for (const el of bar.querySelectorAll("button")) {
      el.onmousedown = null;
      el.onclick = null;
    }
    // V5-3: document.body 가 아니라 parentElement 안에 만들었으므로 확실히 제거된다
    root.remove();
  };
}
