// Measures the slide on screen; mkdeck.check evaluates this in headless Chromium.
// One record per call, read by slide_flags() and _format_row() in check.py.
() => {
  const slide = document.querySelector('.reveal .slides section.present')
             || document.querySelector('.reveal .slides section');
  if (!slide) { return {error: 'no visible slide'}; }
  const vh = window.innerHeight, vw = window.innerWidth;
  const style = getComputedStyle(slide);
  const padTop = parseFloat(style.paddingTop) || 0;
  const padBottom = parseFloat(style.paddingBottom) || 0;
  const body = slide.querySelector('.mkd-body') || slide;
  const kids = Array.from(body.children).filter(k => k.getClientRects().length);
  let top = Infinity, bottom = -Infinity, left = Infinity, right = -Infinity;
  for (const k of kids) {
    const r = k.getBoundingClientRect();
    if (r.height === 0 && r.width === 0) { continue; }
    top = Math.min(top, r.top); bottom = Math.max(bottom, r.bottom);
    left = Math.min(left, r.left); right = Math.max(right, r.right);
  }
  if (!isFinite(top)) { top = 0; bottom = 0; left = 0; right = 0; }
  const scrollers = [];
  for (const e of slide.querySelectorAll('*')) {
    const cs = getComputedStyle(e);
    const canScroll = /(auto|scroll)/.test(cs.overflowX + cs.overflowY);
    if (canScroll && (e.scrollWidth > e.clientWidth + 1 || e.scrollHeight > e.clientHeight + 1)) {
      scrollers.push({tag: e.tagName.toLowerCase(), cls: e.className.toString().slice(0, 40),
                      sw: e.scrollWidth, cw: e.clientWidth, sh: e.scrollHeight, ch: e.clientHeight});
    }
  }
  const overlaps = [];
  const boxes = kids.map(k => k.getBoundingClientRect()).filter(r => r.height > 0);
  for (let i = 0; i < boxes.length; i++) {
    for (let j = i + 1; j < boxes.length; j++) {
      const a = boxes[i], b = boxes[j];
      const ox = Math.min(a.right, b.right) - Math.max(a.left, b.left);
      const oy = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
      if (ox > 2 && oy > 2) { overlaps.push({i: i, j: j, ox: Math.round(ox), oy: Math.round(oy)}); }
    }
  }
  const chrome = document.querySelector('.mkd-chrome-left') || document.querySelector('.mkd-chrome');
  const chromeTop = chrome ? chrome.getBoundingClientRect().top : vh - 34;
  const sentence = Array.from(slide.querySelectorAll('.mkd-sentence')).map(p => p.innerText).join(' ');
  const bullets = Array.from(slide.querySelectorAll('.mkd-bullets li')).map(li => li.innerText);
  const table = slide.querySelector('.mkd-table');
  const left_text = chrome ? chrome.textContent : '';
  const rightChrome = document.querySelector('.mkd-chrome-right');
  const maths = Array.from(slide.querySelectorAll('.mkd-math'));
  // A rollout that is not ready by now failed to load, or is still loading.
  const rollouts = Array.from(slide.querySelectorAll('deck-rollout[src]'))
    .filter(h => h.dataset.mkdState !== 'ready')
    .map(h => {
      const note = h.querySelector('.mkd-rollout-error');
      return {src: h.getAttribute('src'), state: h.dataset.mkdState || 'unloaded',
              message: note ? note.textContent.replace(/^rollout: /, '') : ''};
    });
  return {
    vw: vw, vh: vh,
    top: Math.round(top), bottom: Math.round(bottom), left: Math.round(left), right: Math.round(right),
    overflow_top: Math.round(Math.max(0, padTop - top)),
    overflow_bottom: Math.round(Math.max(0, bottom - (vh - padBottom))),
    into_chrome: bottom > chromeTop,
    scrollers: scrollers,
    overlaps: overlaps,
    sentence_chars: sentence.length,
    bullets: bullets.length,
    bullet_chars: bullets.map(b => b.length),
    table: table ? {rows: table.querySelectorAll('tbody tr').length,
                    cols: table.querySelectorAll('thead th').length,
                    width: Math.round(table.getBoundingClientRect().width)} : null,
    figures: slide.querySelectorAll('.mkd-figure').length,
    formula_blocks: slide.querySelectorAll('.mkd-math-block').length,
    katex_errors: slide.querySelectorAll('.katex-error').length,
    mermaid_errors: slide.querySelectorAll('deck-mermaid[data-mkd-state="error"]').length,
    math_unrendered: maths.filter(m => !m.querySelector('.katex')).length,
    layout: slide.dataset.layout || '',
    id: slide.dataset.id || '',
    dense: slide.classList.contains('dense'),
    rollout_errors: rollouts,
    chrome_left: left_text, chrome_right: rightChrome ? rightChrome.textContent : ''
  };
}
