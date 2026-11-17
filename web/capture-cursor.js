"use strict";
// Recording-only fallback: a plain arrow follows actual pointer events.
// It does not drive the UI or add click effects. Normal app use is unchanged.
if (new URLSearchParams(location.search).has('capture')) {
  document.documentElement.classList.add('capture-mode');
  const style = document.createElement('style');
  style.textContent = '.capture-mode #codex-agent-overlay-root{display:none!important}.capture-mode,.capture-mode *{cursor:none!important}#capture-pointer{position:fixed;left:0;top:0;width:20px;height:27px;z-index:2147483647;pointer-events:none;display:none}';
  document.head.append(style);
  const pointer = document.createElement('div');
  pointer.id = 'capture-pointer';
  pointer.setAttribute('aria-hidden','true');
  pointer.innerHTML = '<svg viewBox="0 0 20 27" width="20" height="27"><path d="M1 1 L1 21 L6 16 L10 25 L13 23.5 L9 15 L17 15 Z" fill="white" stroke="black" stroke-width="1.2" stroke-linejoin="round"/></svg>';
  document.body.append(pointer);
  const record = document.createElement('script');
  record.id = 'capture-events'; record.type = 'application/json'; record.textContent = '[]';
  document.body.append(record);
  const events = [];
  function log(type, data) { events.push({type, epoch:Date.now()/1000,...data}); record.textContent=JSON.stringify(events); }
  document.addEventListener('pointermove', event => {
    pointer.style.display = 'block';
    pointer.style.transform = `translate(${event.clientX}px,${event.clientY}px)`;
  }, true);
  document.addEventListener('pointerdown', event => log('click',{x:event.clientX,y:event.clientY,
    target:event.target.closest('button')?.id || event.target.closest('button')?.textContent || event.target.tagName}),true);
  for (const media of document.querySelectorAll('video,audio')) {
    for (const type of ['playing','pause','seeked','ended']) media.addEventListener(type, () =>
      log(type,{sample:media.tagName==='VIDEO'?'real':'controlled',time:media.currentTime}));
  }
}
