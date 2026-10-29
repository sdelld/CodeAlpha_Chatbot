/*
 * Nova chat widget — drop-in for any website:
 *   <script src="https://YOUR-BOT-HOST/static/widget.js" data-api="https://YOUR-BOT-HOST" defer></script>
 * No dependencies. Conversation is kept for the browser tab session.
 */
(function () {
  var script = document.currentScript;
  var API = (script && script.getAttribute('data-api')) || '';
  var TITLE = (script && script.getAttribute('data-title')) || 'Nova Assistant';
  var STORE_KEY = 'nova-chat-v1';

  var css = `
  .nv-launch{position:fixed;right:20px;bottom:20px;width:60px;height:60px;border-radius:50%;border:0;cursor:pointer;
    background:#4f46e5;color:#fff;font-size:26px;box-shadow:0 8px 24px rgba(79,70,229,.45);z-index:2147483000;transition:transform .15s}
  .nv-launch:hover{transform:scale(1.06)} .nv-launch:focus-visible{outline:3px solid #a5b4fc;outline-offset:3px}
  .nv-badge{position:absolute;top:2px;right:2px;width:14px;height:14px;border-radius:50%;background:#ef4444;border:2px solid #fff}
  .nv-panel{position:fixed;right:20px;bottom:92px;width:370px;max-width:calc(100vw - 32px);height:540px;max-height:calc(100vh - 120px);
    background:#fff;border-radius:18px;box-shadow:0 20px 50px rgba(15,23,42,.25);display:flex;flex-direction:column;overflow:hidden;
    z-index:2147483000;font:15px/1.45 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;color:#0f172a}
  .nv-panel[hidden]{display:none}
  .nv-head{background:#4f46e5;color:#fff;padding:14px 16px;display:flex;align-items:center;gap:10px}
  .nv-head b{flex:1;font-size:16px} .nv-head small{display:block;opacity:.85;font-weight:400;font-size:12px}
  .nv-head button{background:none;border:0;color:#fff;font-size:22px;cursor:pointer;line-height:1}
  .nv-log{flex:1;overflow-y:auto;padding:16px;display:flex;flex-direction:column;gap:10px;background:#f8fafc}
  .nv-msg{max-width:82%;padding:9px 13px;border-radius:14px;white-space:pre-wrap;word-wrap:break-word}
  .nv-bot{background:#fff;border:1px solid #e2e8f0;align-self:flex-start;border-bottom-left-radius:4px}
  .nv-user{background:#4f46e5;color:#fff;align-self:flex-end;border-bottom-right-radius:4px}
  .nv-meta{align-self:flex-start;display:flex;gap:4px;margin-top:-6px}
  .nv-meta button{background:none;border:0;cursor:pointer;font-size:13px;opacity:.55;padding:2px 4px}
  .nv-meta button:hover{opacity:1} .nv-meta .on{opacity:1}
  .nv-chips{display:flex;flex-wrap:wrap;gap:6px;align-self:flex-start}
  .nv-chips button{border:1px solid #c7d2fe;background:#eef2ff;color:#3730a3;border-radius:999px;padding:5px 11px;cursor:pointer;font:inherit;font-size:13px}
  .nv-chips button:hover{background:#e0e7ff}
  .nv-typing{align-self:flex-start;background:#fff;border:1px solid #e2e8f0;border-radius:14px;padding:10px 14px}
  .nv-typing i{display:inline-block;width:6px;height:6px;margin:0 2px;border-radius:50%;background:#94a3b8;animation:nvb 1s infinite}
  .nv-typing i:nth-child(2){animation-delay:.15s} .nv-typing i:nth-child(3){animation-delay:.3s}
  @keyframes nvb{0%,80%,100%{transform:translateY(0)}40%{transform:translateY(-5px)}}
  .nv-form{display:flex;gap:8px;padding:12px;border-top:1px solid #e2e8f0;background:#fff}
  .nv-form input{flex:1;border:1px solid #cbd5e1;border-radius:999px;padding:10px 14px;font:inherit;outline:none;min-width:0}
  .nv-form input:focus{border-color:#4f46e5}
  .nv-form button{border:0;background:#4f46e5;color:#fff;border-radius:999px;padding:0 16px;font:inherit;font-weight:600;cursor:pointer}
  .nv-form button:disabled{opacity:.5}
  @media (max-width:480px){.nv-panel{right:0;bottom:0;width:100vw;max-width:100vw;height:100%;max-height:100%;border-radius:0}}
  `;
  var style = document.createElement('style'); style.textContent = css; document.head.appendChild(style);

  var launch = el('button', 'nv-launch', '💬');
  launch.setAttribute('aria-label', 'Open chat'); launch.setAttribute('aria-expanded', 'false');
  var badge = el('span', 'nv-badge'); launch.appendChild(badge);

  var panel = el('div', 'nv-panel'); panel.hidden = true;
  panel.setAttribute('role', 'dialog'); panel.setAttribute('aria-label', TITLE);
  var head = el('div', 'nv-head');
  head.innerHTML = '<span style="font-size:24px">🤖</span>';
  var title = el('b', '', TITLE); title.appendChild(el('small', '', 'Typically replies instantly'));
  var close = el('button', '', '×'); close.setAttribute('aria-label', 'Close chat');
  head.appendChild(title); head.appendChild(close);
  var log = el('div', 'nv-log'); log.setAttribute('aria-live', 'polite');
  var form = el('form', 'nv-form');
  var input = el('input'); input.placeholder = 'Type your question…'; input.maxLength = 500;
  input.setAttribute('aria-label', 'Message');
  var send = el('button', '', 'Send'); send.type = 'submit';
  form.appendChild(input); form.appendChild(send);
  panel.appendChild(head); panel.appendChild(log); panel.appendChild(form);
  document.body.appendChild(launch); document.body.appendChild(panel);

  var state = load() || { history: [], context: null };
  if (state.history.length) { state.history.forEach(function (m) { render(m, false); }); }
  else {
    addBot({ reply: "Hi! 👋 I'm Nova, your shopping assistant. How can I help?",
             suggestions: ['Track my order', 'Shipping times', 'Return policy', 'Payment methods'] });
  }

  launch.addEventListener('click', function () { toggle(panel.hidden); });
  close.addEventListener('click', function () { toggle(false); });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && !panel.hidden) toggle(false); });
  form.addEventListener('submit', function (e) { e.preventDefault(); ask(input.value); });

  function toggle(open) {
    panel.hidden = !open; launch.setAttribute('aria-expanded', String(open));
    badge.style.display = 'none';
    if (open) { input.focus(); log.scrollTop = log.scrollHeight; }
  }

  function ask(text) {
    text = (text || '').trim(); if (!text) return;
    input.value = ''; send.disabled = true;
    addMessage({ from: 'user', text: text });
    var typing = el('div', 'nv-typing', '<i></i><i></i><i></i>', true); log.appendChild(typing); scroll();
    var started = Date.now();
    fetch(API + '/api/chat', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text, context: state.context })
    }).then(function (r) { return r.json(); }).then(function (d) {
      // A short, natural pause so the reply doesn't feel abrupt.
      setTimeout(function () {
        typing.remove();
        if (d.error) { addBot({ reply: d.error }); return; }
        state.context = d.context || null;
        addBot(d);
      }, Math.max(0, 450 - (Date.now() - started)));
    }).catch(function () {
      typing.remove(); addBot({ reply: "I can't connect right now. Please try again in a moment." });
    }).finally(function () { send.disabled = false; input.focus(); });
  }

  function addBot(d) {
    addMessage({ from: 'bot', text: d.reply, id: d.id, intent: d.intent, suggestions: d.suggestions || [] });
  }

  function addMessage(m) { state.history.push(m); state.history = state.history.slice(-60); save(); render(m, true); }

  function render(m, fresh) {
    log.appendChild(el('div', 'nv-msg ' + (m.from === 'user' ? 'nv-user' : 'nv-bot'), m.text));
    if (m.from === 'bot' && m.id) {
      var meta = el('div', 'nv-meta');
      [['👍', true], ['👎', false]].forEach(function (pair) {
        var b = el('button', '', pair[0]); b.setAttribute('aria-label', pair[1] ? 'Helpful' : 'Not helpful');
        b.addEventListener('click', function () {
          meta.querySelectorAll('button').forEach(function (x) { x.disabled = true; });
          b.className = 'on';
          fetch(API + '/api/feedback', { method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id: m.id, intent: m.intent, helpful: pair[1] }) }).catch(function () {});
        });
        meta.appendChild(b);
      });
      log.appendChild(meta);
    }
    if (fresh && m.suggestions && m.suggestions.length) {
      var chips = el('div', 'nv-chips');
      m.suggestions.forEach(function (s) {
        var c = el('button', '', s); c.type = 'button';
        c.addEventListener('click', function () { chips.remove(); ask(s); });
        chips.appendChild(c);
      });
      log.appendChild(chips);
    }
    scroll();
  }

  function scroll() { log.scrollTop = log.scrollHeight; }
  function el(tag, cls, content, html) {
    var n = document.createElement(tag); if (cls) n.className = cls;
    if (content) { if (html) n.innerHTML = content; else n.textContent = content; }
    return n;
  }
  function save() { try { sessionStorage.setItem(STORE_KEY, JSON.stringify(state)); } catch (e) {} }
  function load() { try { return JSON.parse(sessionStorage.getItem(STORE_KEY)); } catch (e) { return null; } }

  window.NovaChat = { open: function () { toggle(true); }, ask: function (t) { toggle(true); ask(t); } };
})();
