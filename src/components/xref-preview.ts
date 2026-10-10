/**
 * xref 悬浮预览卡片（vanilla TS，BaseLayout 以 <script> 引入，Astro 自动打包）。
 *
 * 行为：桌面端悬停/聚焦 a.xref-link 时 fetch /api/xref?key=… 并弹出卡片，
 * 展示定理完整陈述（KaTeX 已渲染）；移动端（<768px 或 coarse pointer）
 * 不弹卡，点击直接导航。Esc / 滚动 / 移出（200ms 宽限）关闭。
 */

interface XrefData {
  url: string;
  label: string;
  articleTitle: string;
  excerptHtml: string;
}

const cache = new Map<string, Promise<XrefData | null>>();

let card: HTMLDivElement | null = null;
let hideTimer: number | undefined;
let showTimer: number | undefined;
let activeLink: HTMLElement | null = null;

function isMobile(): boolean {
  return (
    window.innerWidth < 768 ||
    window.matchMedia("(pointer: coarse)").matches
  );
}

function fetchXref(key: string): Promise<XrefData | null> {
  let p = cache.get(key);
  if (!p) {
    p = fetch(`/api/xref?key=${encodeURIComponent(key)}`)
      .then((r) => (r.ok ? (r.json() as Promise<XrefData>) : null))
      .catch(() => null);
    cache.set(key, p);
  }
  return p;
}

function ensureCard(): HTMLDivElement {
  if (card) return card;
  card = document.createElement("div");
  card.className = "xref-card";
  card.setAttribute("role", "tooltip");
  card.id = "xref-preview-card";
  card.hidden = true;
  // 鼠标可移入卡片（宽限期内取消隐藏）
  card.addEventListener("pointerenter", () => {
    window.clearTimeout(hideTimer);
  });
  card.addEventListener("pointerleave", () => scheduleHide());
  document.body.appendChild(card);
  return card;
}

function positionCard(link: HTMLElement, el: HTMLDivElement) {
  const GAP = 8;
  const rect = link.getBoundingClientRect();
  const elRect = el.getBoundingClientRect();
  const scrollX = window.scrollX;
  const scrollY = window.scrollY;

  // 默认链接下方；视口底部放不下则翻转到上方
  let top = rect.bottom + GAP;
  if (rect.bottom + GAP + elRect.height > window.innerHeight) {
    const flipped = rect.top - GAP - elRect.height;
    if (flipped >= 0) top = flipped;
  }
  // 左对齐链接；右侧超出则右移回收
  let left = rect.left;
  if (left + elRect.width > window.innerWidth - GAP) {
    left = Math.max(GAP, window.innerWidth - elRect.width - GAP);
  }

  el.style.top = `${top + scrollY}px`;
  el.style.left = `${left + scrollX}px`;
}

async function show(link: HTMLElement) {
  const key = link.dataset.xrefKey;
  if (!key) return;
  const data = await fetchXref(key);
  // 等待期间鼠标可能已移开或移到别的链接
  if (!data || activeLink !== link) return;

  const el = ensureCard();
  el.innerHTML = "";

  const label = document.createElement("div");
  label.className = "xref-card-label";
  label.textContent = data.label;

  const excerpt = document.createElement("div");
  excerpt.className = "xref-card-excerpt";
  // excerptHtml 由本站 API 生成（正文转义 + KaTeX 渲染），可信
  excerpt.innerHTML = data.excerptHtml;

  const source = document.createElement("div");
  source.className = "xref-card-source";
  source.textContent = data.articleTitle;

  el.append(label, excerpt, source);

  link.setAttribute("aria-describedby", el.id);
  el.hidden = false;
  positionCard(link, el);
}

function scheduleShow(link: HTMLElement) {
  window.clearTimeout(hideTimer);
  window.clearTimeout(showTimer);
  if (activeLink === link && card && !card.hidden) return;
  activeLink = link;
  showTimer = window.setTimeout(() => void show(link), 150);
}

function hide() {
  window.clearTimeout(showTimer);
  window.clearTimeout(hideTimer);
  if (activeLink) {
    activeLink.removeAttribute("aria-describedby");
    activeLink = null;
  }
  if (card) card.hidden = true;
}

function scheduleHide() {
  window.clearTimeout(hideTimer);
  hideTimer = window.setTimeout(hide, 200);
}

document.addEventListener("pointerover", (e) => {
  if (isMobile()) return;
  const link = (e.target as HTMLElement)?.closest?.("a.xref-link");
  if (link) {
    scheduleShow(link as HTMLElement);
    return;
  }
  // 移到非卡片区域时隐藏（卡片自身的 pointerleave 另有处理）
  if (activeLink && !(e.relatedTarget as HTMLElement)?.closest?.(".xref-card")) {
    scheduleHide();
  }
});

document.addEventListener("focusin", (e) => {
  if (isMobile()) return;
  const link = (e.target as HTMLElement)?.closest?.("a.xref-link");
  if (link) scheduleShow(link as HTMLElement);
});

document.addEventListener("focusout", (e) => {
  const link = (e.target as HTMLElement)?.closest?.("a.xref-link");
  if (link) scheduleHide();
});

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") hide();
});

window.addEventListener(
  "scroll",
  (e) => {
    // 卡片内部滚动（overflow-y）不关闭
    if ((e.target as HTMLElement)?.closest?.(".xref-card")) return;
    hide();
  },
  { passive: true, capture: true }
);
window.addEventListener("resize", hide);
