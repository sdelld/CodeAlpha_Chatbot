/*
 * Nova chat widget v2 — drop-in for any website:
 *   <script src="https://YOUR-BOT-HOST/static/widget.js" data-api="https://YOUR-BOT-HOST" defer></script>
 * Streams replies (server-sent events), shows product cards and quick replies, supports Arabic (RTL).
 */
(function () {
  var script = document.currentScript;
  var API = (script && script.getAttribute("data-api")) || "";
  var TITLE = (script && script.getAttribute("data-title")) || "Nova Assistant";
  var KEY = "nova-chat-v2";

  var css = `
  .nv-launch{position:fixed;inset-inline-end:20px;bottom:20px;width:60px;height:60px;border-radius:50%;border:0;cursor:pointer;
    background:#4f46e5;color:#fff;font-size:26px;box-shadow:0 8px 24px rgba(79,70,229,.45);z-index:2147483000;transition:transform .15s}
  .nv-launch:hover{transform:scale(1.06)} .nv-launch:focus-visible,.nv-panel button:focus-visible{outline:3px solid #a5b4fc;outline-offset:2px}
  .nv-panel{position:fixed;inset-inline-end:20px;bottom:92px;width:390px;max-width:calc(100vw - 32px);height:600px;max-height:calc(100vh - 120px);
    background:#fff;border-radius:18px;box-shadow:0 20px 50px rgba(15,23,42,.25);display:flex;flex-direction:column;overflow:hidden;
    z-index:2147483000;font:15px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,"Noto Sans Arabic",Tahoma,sans-serif;color:#0f172a}
  .nv-panel[hidden]{display:none}
  .nv-head{background:#4f46e5;color:#fff;padding:14px 16px;display:flex;align-items:center;gap:10px}
  .nv-head b{flex:1;font-size:16px} .nv-head small{display:block;opacity:.85;font-weight:400;font-size:12px}
  .nv-head button{background:none;border:0;color:#fff;font-size:22px;cursor:pointer;line-height:1;padding:4px}
  .nv-log{flex:1;overflow-y:auto;padding:14px;display:flex;flex-direction:column;gap:10px;background:#f8fafc}
  .nv-msg{max-width:86%;padding:9px 13px;border-radius:14px;word-wrap:break-word;white-space:pre-wrap}
  .nv-bot{background:#fff;border:1px solid #e2e8f0;align-self:flex-start;border-end-start-radius:4px}
  .nv-user{background:#4f46e5;color:#fff;align-self:flex-end;border-end-end-radius:4px}
  .nv-msg{text-align:start}
  .nv-cards{display:flex;gap:8px;overflow-x:auto;align-self:stretch;padding-bottom:4px}
  .nv-card{flex:0 0 165px;background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:10px;font-size:13px}
  .nv-card b{display:block;font-size:14px;margin-bottom:2px} .nv-card .p{color:#4f46e5;font-weight:800;font-size:15px}
  .nv-card .s{color:#64748b;font-size:12px;margin-top:4px} .nv-card .st{font-size:11px;font-weight:700;margin-top:6px}
  .nv-card .in{color:#047857} .nv-card .out{color:#b91c1c}
  .nv-card button{margin-top:8px;width:100%;border:1px solid #c7d2fe;background:#eef2ff;color:#3730a3;border-radius:8px;padding:4px;cursor:pointer;font:inherit;font-size:12px}
  .nv-meta{align-self:flex-start;display:flex;gap:4px;margin-top:-6px}
  .nv-meta button{background:none;border:0;cursor:pointer;font-size:13px;opacity:.55;padding:2px 4px}
  .nv-meta button:hover,.nv-meta .on{opacity:1}
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
  @media (max-width:480px){.nv-panel{inset-inline-end:0;bottom:0;width:100vw;max-width:100vw;height:100%;max-height:100%;border-radius:0}}
  @media (prefers-reduced-motion:reduce){.nv-typing i{animation:none}}
  `;
  var style = document.createElement("style"); style.textContent = css; document.head.appendChild(style);

  var launch = el("button", "nv-launch", "💬");
  launch.setAttribute("aria-label", "Open chat"); launch.setAttribute("aria-expanded", "false");
  var panel = el("div", "nv-panel"); panel.hidden = true;
  panel.setAttribute("role", "dialog"); panel.setAttribute("aria-label", TITLE);
  var head = el("div", "nv-head");
  head.appendChild(el("span", "", "🤖"));
  var title = el("b", "", TITLE); title.appendChild(el("small", "", "English · العربية · Arabizi"));
  var close = el("button", "", "×"); close.setAttribute("aria-label", "Close chat");
  head.appendChild(title); head.appendChild(close);
  var log = el("div", "nv-log"); log.setAttribute("aria-live", "polite");
  var form = el("form", "nv-form");
  var input = el("input"); input.placeholder = "Ask about products, orders, delivery… / اسأل هنا"; input.maxLength = 1000;
  input.setAttribute("aria-label", "Message");
  var send = el("button", "", "Send"); send.type = "submit";
  form.appendChild(input); form.appendChild(send);
  panel.appendChild(head); panel.appendChild(log); panel.appendChild(form);
  document.body.appendChild(launch); document.body.appendChild(panel);

  var state = load() || { sessionId: null, history: [] };
  if (state.history.length) state.history.forEach(function (m) { render(m, false); });
  else addBot({ text: "Hi! 👋 I'm Nova. Ask me about products, prices, stock, orders, delivery or warranty — in English or Arabic.\nأهلاً! اسألني بالعربي أو بالإنجليزي.",
                suggestions: ["Noise cancelling headphones", "Laptops under 30000 EGP", "Track my order", "عايز موبايل في حدود 15 ألف"] });

  launch.addEventListener("click", function () { toggle(panel.hidden); });
  close.addEventListener("click", function () { toggle(false); });
  document.addEventListener("keydown", function (e) { if (e.key === "Escape" && !panel.hidden) toggle(false); });
  form.addEventListener("submit", function (e) { e.preventDefault(); ask(input.value); });

  function toggle(open) {
    panel.hidden = !open; launch.setAttribute("aria-expanded", String(open));
    if (open) { input.focus(); scroll(); }
  }

  async function ask(text) {
    text = (text || "").trim(); if (!text) return;
    input.value = ""; send.disabled = true;
    addMessage({ from: "user", text: text });
    var typing = el("div", "nv-typing"); typing.innerHTML = "<i></i><i></i><i></i>"; log.appendChild(typing); scroll();
    var bubble = null, msg = { from: "bot", text: "", products: [], suggestions: [], question: text };
    function ensureBubble() {
      if (!bubble) { typing.remove(); bubble = el("div", "nv-msg nv-bot"); log.appendChild(bubble); }
      return bubble;
    }
    try {
      var resp = await fetch(API + "/api/chat/stream", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, session_id: state.sessionId }) });
      if (!resp.ok || !resp.body) {
        var err = await resp.json().catch(function () { return {}; });
        throw new Error(err.error || "Request failed");
      }
      var reader = resp.body.getReader(), decoder = new TextDecoder(), buf = "";
      while (true) {
        var chunk = await reader.read();
        if (chunk.done) break;
        buf += decoder.decode(chunk.value, { stream: true });
        var events = buf.split("\n\n"); buf = events.pop();
        events.forEach(function (raw) {
          var line = raw.split("\n").find(function (l) { return l.indexOf("data: ") === 0; });
          if (!line) return;
          var ev = JSON.parse(line.slice(6));
          if (ev.type === "meta") { state.sessionId = ev.session_id; }
          else if (ev.type === "token") { msg.text += ev.text; paint(ensureBubble(), msg.text); scroll(); }
          else if (ev.type === "replace") { msg.text = ev.text || ""; if (msg.text) paint(ensureBubble(), msg.text); }
          else if (ev.type === "products") { msg.products = ev.items; }
          else if (ev.type === "suggestions") { msg.suggestions = ev.items; }
          else if (ev.type === "done") { msg.text = ev.reply; }
        });
      }
      if (bubble) bubble.remove(); else typing.remove();
      addMessage(msg);
    } catch (e) {
      typing.remove(); if (bubble) bubble.remove();
      addBot({ text: navigator.onLine ? "Sorry, something went wrong. Please try again in a moment." : "You seem to be offline. Please check your connection." });
    } finally { send.disabled = false; input.focus(); }
  }

  function addBot(m) { m.from = "bot"; addMessage(m); }
  function addMessage(m) { state.history.push(m); state.history = state.history.slice(-50); save(); render(m, true); }

  function paint(node, text) {
    // Escape everything, then allow **bold** only — never inject raw HTML from the model.
    var safe = text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/\*\*(.+?)\*\*/g, "<b>$1</b>");
    node.innerHTML = safe;
    node.dir = "auto"; // direction follows the first word: Arabic replies RTL, English LTR
  }

  function render(m, fresh) {
    var bubble = el("div", "nv-msg " + (m.from === "user" ? "nv-user" : "nv-bot"));
    if (m.from === "user") { bubble.textContent = m.text; bubble.dir = "auto"; }
    else paint(bubble, m.text || "");
    log.appendChild(bubble);
    if (m.products && m.products.length) {
      var row = el("div", "nv-cards");
      m.products.forEach(function (p) {
        var c = el("div", "nv-card");
        c.appendChild(el("b", "", p.name));
        c.appendChild(el("div", "p", Number(p.price_egp).toLocaleString("en-US") + " EGP"));
        var specs = p.key_specs ? Object.values(p.key_specs).slice(0, 2).join(" · ") : "";
        if (specs) c.appendChild(el("div", "s", specs));
        c.appendChild(el("div", "st " + (p.in_stock ? "in" : "out"), p.in_stock ? "In stock" : "Out of stock"));
        var more = el("button", "", "Details"); more.type = "button";
        more.addEventListener("click", function () { ask("Tell me about the " + p.name); });
        c.appendChild(more);
        row.appendChild(c);
      });
      log.appendChild(row);
    }
    if (m.from === "bot" && m.question) {
      var meta = el("div", "nv-meta");
      [["👍", true], ["👎", false]].forEach(function (pair) {
        var b = el("button", "", pair[0]); b.setAttribute("aria-label", pair[1] ? "Helpful" : "Not helpful");
        b.addEventListener("click", function () {
          meta.querySelectorAll("button").forEach(function (x) { x.disabled = true; }); b.className = "on";
          fetch(API + "/api/feedback", { method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ session_id: state.sessionId, message: m.question, helpful: pair[1] }) }).catch(function () {});
        });
        meta.appendChild(b);
      });
      log.appendChild(meta);
    }
    if (fresh && m.suggestions && m.suggestions.length) {
      var chips = el("div", "nv-chips");
      m.suggestions.forEach(function (s) {
        var c = el("button", "", s); c.type = "button";
        c.addEventListener("click", function () { chips.remove(); ask(s); });
        chips.appendChild(c);
      });
      log.appendChild(chips);
    }
    scroll();
  }

  function scroll() { log.scrollTop = log.scrollHeight; }
  function el(tag, cls, text) { var n = document.createElement(tag); if (cls) n.className = cls; if (text) n.textContent = text; return n; }
  function save() { try { sessionStorage.setItem(KEY, JSON.stringify(state)); } catch (e) {} }
  function load() { try { return JSON.parse(sessionStorage.getItem(KEY)); } catch (e) { return null; } }

  window.NovaChat = { open: function () { toggle(true); }, ask: function (t) { toggle(true); ask(t); } };
})();
