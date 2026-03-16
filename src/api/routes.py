from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import time
import functools
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
import asyncio
import json

from src.constants import X_REQUEST_ID_HEADER, X_CHANNEL_ID_HEADER, MISSING_HEADERS_ERROR, DEFAULT_EXECUTION_BUDGET_MS
from src.services.conversation_service import conversation_service
from src.observability.logger import get_logger
from src.observability.tracer import get_tracer
from src.agent.nodes import register_token_queue, deregister_token_queue

router = APIRouter()


def profile_api(fn):
    @functools.wraps(fn)
    async def wrapper(*args, **kwargs):
        logger = get_logger()
        start = time.time()
        result = await fn(*args, **kwargs)
        elapsed_ms = (time.time() - start) * 1000
        logger.info("api.profile", fn=fn.__name__, elapsed_ms=elapsed_ms)
        return result
    return wrapper



class ConversationTurn(BaseModel):
    conversation_id: str = Field(default="")
    user_id: str = Field(default="user-1")
    session_id: str = Field(default="session-1")
    order_id: Optional[str] = None
    product_id: Optional[str] = None
    payload: Optional[Dict[str, Any]] = None
    message: str
    messages: List[Dict[str, str]] = Field(default_factory=list)
    execution_budget_ms: int = DEFAULT_EXECUTION_BUDGET_MS


class ConversationResponse(BaseModel):
    conversation_id: str
    user_id: str
    session_id: str
    final_response: str
    next_node: str
    escalation_required: bool = False
    tool_results: Dict[str, Any] = Field(default_factory=dict)
    trace_id: str
    response_source: str = ""
    timings_ms: Dict[str, Any] = Field(default_factory=dict)
    emotion: Optional[Dict[str, Any]] = None
    escalation_packet: Optional[Dict[str, Any]] = None


@router.get("/health")
@profile_api
async def health_check(request: Request):
    logger = getattr(request.state, "logger", get_logger())
    logger.info("health_check", status="ok")
    return {"status": "ok"}


@router.get("/metrics")
def metrics():
    data = generate_latest()
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)


@router.get("/ui", response_class=HTMLResponse)
def ui():
    html = """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8"/>
    <meta name="viewport" content="width=device-width, initial-scale=1"/>
    <title>ecom-cst-asst-agent E2E Console</title>
    <style>
      :root {
        --ink: #1b1b1b;
        --paper: #f5f1e8;
        --accent: #d95d39;
        --accent-2: #355c7d;
        --muted: #6b6b6b;
        --card: #fffaf1;
        --border: #e5dccb;
      }
      * { box-sizing: border-box; }
      body {
        margin: 0;
        font-family: "Space Grotesk", "Avenir Next", "Segoe UI", sans-serif;
        color: var(--ink);
        background: radial-gradient(circle at 10% 20%, #fff 0, var(--paper) 40%, #f1e6d7 100%);
      }
      header {
        padding: 28px 32px 8px;
      }
      h1 {
        margin: 0 0 6px;
        font-size: 28px;
        letter-spacing: 0.5px;
      }
      .sub {
        color: var(--muted);
        font-size: 14px;
      }
      main {
        display: grid;
        grid-template-columns: minmax(320px, 0.9fr) minmax(420px, 1.4fr);
        gap: 18px;
        padding: 16px 32px 32px;
        align-items: stretch;
        min-height: calc(100vh - 140px);
      }
      .card {
        background: var(--card);
        border: 1px solid var(--border);
        border-radius: 14px;
        padding: 16px;
        box-shadow: 0 8px 24px rgba(0,0,0,0.06);
      }
      .stack {
        display: grid;
        grid-template-rows: minmax(140px, 220px) minmax(120px, 1fr);
        gap: 12px;
        height: 100%;
      }
      .chat-wrap {
        display: flex;
        flex-direction: column;
        gap: 10px;
        height: 100%;
      }
      .chat-box {
        border: 1px solid var(--border);
        border-radius: 10px;
        padding: 10px;
        min-height: 320px;
        flex: 1;
        min-height: 420px;
        background: #fff;
        overflow-y: auto;
      }
      .chat-actions {
        display: grid;
        grid-template-columns: 1fr auto auto;
        gap: 10px;
        align-items: center;
        position: sticky;
        bottom: 0;
        background: var(--card);
        padding-top: 6px;
      }
      .bubble {
        margin: 6px 0;
        padding: 8px 10px;
        border-radius: 8px;
        line-height: 1.35;
        white-space: pre-wrap;
        word-break: break-word;
      }
      .bubble.user { background: #f0e7d9; }
      .bubble.assistant { background: #e7f0ff; }
      label { font-size: 12px; color: var(--muted); }
      textarea, input {
        width: 100%;
        border-radius: 10px;
        border: 1px solid var(--border);
        padding: 10px 12px;
        font-family: "JetBrains Mono", "SF Mono", monospace;
        font-size: 12px;
        background: #fff;
        color: var(--ink);
      }
      textarea { min-height: 220px; }
      .row { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 10px; }
      .actions { display: flex; gap: 10px; align-items: center; margin-top: 8px; }
      button {
        border: none;
        border-radius: 10px;
        padding: 10px 14px;
        font-weight: 600;
        cursor: pointer;
        color: #fff;
        background: var(--accent);
      }
      button.secondary { background: var(--accent-2); }
      pre {
        background: #0f0f0f;
        color: #eaeaea;
        padding: 12px;
        border-radius: 10px;
        overflow-y: auto;
        min-height: 140px;
        height: 180px;
        white-space: pre-wrap;
        word-break: break-word;
      }
      .pill {
        display: inline-block;
        padding: 4px 8px;
        border-radius: 999px;
        font-size: 11px;
        background: #f0e7d9;
        border: 1px solid var(--border);
      }
      @media (max-width: 980px) {
        main { grid-template-columns: 1fr; }
        .chat-wrap { grid-template-rows: minmax(260px, 1fr) auto; }
      }
    </style>
  </head>
  <body>
    <header>
      <h1>ecom-cst-asst-agent E2E Console</h1>
      <div class="sub">Send requests to <span class="pill">/support</span> and inspect response + logs.</div>
    </header>
    <main>
      <section class="card">
        <div class="row">
          <div>
            <label>Request ID</label>
            <input id="reqId" placeholder="auto-generated"/>
          </div>
          <div>
            <label>Channel ID</label>
            <input id="channelId" value="ui"/>
          </div>
        </div>
        <div class="row">
          <div>
            <label>Conversation ID</label>
            <input id="conversationId" value="ui-1"/>
          </div>
          <div>
            <label>User ID</label>
            <input id="userId" value="USR-00397"/>
          </div>
        </div>
        <div class="row">
          <div>
            <label>Session ID</label>
            <input id="sessionId" value="s1"/>
          </div>
          <div>
            <label>Order ID (optional)</label>
            <input id="orderId" value="N-20260314-ITIKF"/>
          </div>
        </div>
        <label>Configurable Payload</label>
        <textarea id="payload"></textarea>
        <div class="stack" style="margin-top:12px;">
          <div>
            <label>Request + Response</label>
            <pre id="response"></pre>
          </div>
          <div>
            <label>Client Logs</label>
            <pre id="clientLog"></pre>
          </div>
        </div>
      </section>
      <section class="card">
        <label>Chat</label>
        <div class="chat-wrap">
          <div id="chat" class="chat-box"></div>
          <div class="chat-actions">
            <input id="messageInput" placeholder="Type a message... (Press Enter to send)" />
            <button id="sendBtn">Send</button>
            <button class="secondary" id="resetBtn">Reset</button>
          </div>
        </div>
      </section>
    </main>
    <script>
      const chatEl = document.getElementById("chat");
      const payloadEl = document.getElementById("payload");
      const messageInputEl = document.getElementById("messageInput");
      const responseEl = document.getElementById("response");
      const logEl = document.getElementById("clientLog");
      const reqIdEl = document.getElementById("reqId");
      const channelIdEl = document.getElementById("channelId");
      const conversationIdEl = document.getElementById("conversationId");
      const userIdEl = document.getElementById("userId");
      const sessionIdEl = document.getElementById("sessionId");
      const orderIdEl = document.getElementById("orderId");
      let messages = [];
      let typingTimer = null;
      let streamingBubble = null;

      function log(msg) {
        logEl.textContent += msg + "\\n";
        logEl.scrollTop = logEl.scrollHeight;
      }

      function uuid() {
        return "req-" + Math.random().toString(16).slice(2);
      }

      function escapeHtml(text) {
        return text
          .replaceAll("&", "&amp;")
          .replaceAll("<", "&lt;")
          .replaceAll(">", "&gt;");
      }

      function renderMarkdown(text) {
        let html = escapeHtml(text);
        html = html.replace(/^### (.*)$/gm, "<h3>$1</h3>");
        html = html.replace(/^## (.*)$/gm, "<h2>$1</h2>");
        html = html.replace(/^# (.*)$/gm, "<h1>$1</h1>");
        html = html.replace(/\\*\\*(.+?)\\*\\*/g, "<strong>$1</strong>");
        html = html.replace(/\\*(.+?)\\*/g, "<em>$1</em>");
        html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
        html = html.replace(/\\n/g, "<br/>");
        return html;
      }

      function appendBubble(role, content, asMarkdown) {
        const bubble = document.createElement("div");
        bubble.className = `bubble ${role}`;
        if (asMarkdown) {
          bubble.innerHTML = renderMarkdown(content);
        } else {
          bubble.textContent = content;
        }
        chatEl.appendChild(bubble);
        chatEl.scrollTop = chatEl.scrollHeight;
        return bubble;
      }

      function typeAssistant(text) {
        if (typingTimer) {
          clearInterval(typingTimer);
          typingTimer = null;
        }
        const bubble = appendBubble("assistant", "", false);
        let idx = 0;
        typingTimer = setInterval(() => {
          idx += 2;
          bubble.textContent = text.slice(0, idx);
          chatEl.scrollTop = chatEl.scrollHeight;
          if (idx >= text.length) {
            clearInterval(typingTimer);
            typingTimer = null;
            bubble.innerHTML = renderMarkdown(text);
          }
        }, 18);
      }

      function formatTiming(timings) {
        if (!timings) return "";
        const lines = [
          `Intent classification:     ~${Math.round(timings.intent_classification || 0)}ms`,
          `Param extraction:          ~${Math.round(timings.param_extraction || 0)}ms`,
          `DB query:                  ~${Math.round(timings["tool:check_order"] || 0)}ms`,
          `Qdrant RAG retrieval:      ~${Math.round(timings.rag_retrieval || 0)}ms`,
          `LLM generation:            ~${Math.round(timings.llm_generation || 0)}ms`,
          `Persist response:          ~${Math.round(timings.persist_response || 0)}ms`,
          `Total:                     ~${Math.round(timings.generate_response_total || 0) + Math.round(timings.execute_tools_total || 0)}ms`,
        ];
        return lines.join("\\n");
      }

      const thinkingEl = document.createElement("div");
      thinkingEl.style.margin = "6px 0";
      thinkingEl.style.padding = "8px 10px";
      thinkingEl.style.borderRadius = "8px";
      thinkingEl.style.background = "#f8f0df";
      thinkingEl.style.display = "none";
      thinkingEl.textContent = "Thinking...";
      chatEl.parentElement.insertBefore(thinkingEl, chatEl.nextSibling);

      document.getElementById("sendBtn").addEventListener("click", async () => {
        responseEl.textContent = "";
        logEl.textContent = "";
        const reqId = uuid();
        const channelId = channelIdEl.value || "ui";
        reqIdEl.value = reqId;
        const message = messageInputEl.value.trim();
        if (!message) return;
        messages.push({ role: "user", content: message });
        renderChat();
        messageInputEl.value = "";
        let payload;
        try {
          payload = JSON.parse(payloadEl.value || "{}");
        } catch (e) {
          log("Invalid JSON payload");
          return;
        }
        payload.conversation_id = payload.conversation_id || conversationIdEl.value || "ui-1";
        payload.user_id = payload.user_id || userIdEl.value || "USR-00397";
        payload.session_id = payload.session_id || sessionIdEl.value || "s1";
        if (!payload.order_id && orderIdEl.value) payload.order_id = orderIdEl.value;
        payload.message = message;
        payload.messages = messages.slice(0, -1);
        log(`Sending request ${reqId}`);
        const start = performance.now();
        thinkingEl.style.display = "block";
        thinkingEl.textContent = "Thinking...";
        let thinkingTimer = setTimeout(() => {
          thinkingEl.textContent = "Thinking longer to answer...";
        }, 2000);
        const res = await fetch("/support/stream", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "x-request-id": reqId,
            "x-channel-id": channelId
          },
          body: JSON.stringify(payload)
        });
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        let fullText = "";
        let firstChunkAt = null;
        streamingBubble = appendBubble("assistant", "", false);

        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const parts = buffer.split("\\n\\n");
          buffer = parts.pop() || "";
          for (const part of parts) {
            if (part.startsWith("event: meta")) {
              const dataLine = part.split("\\n").find((l) => l.startsWith("data: "));
              if (dataLine) {
                const meta = JSON.parse(dataLine.replace("data: ", ""));
                log(`Status: ${res.status}`);
                log(`Server TTFT: ${Math.round(meta.server_ttft_ms || 0)} ms`);
                if (meta.timings_ms) log(formatTiming(meta.timings_ms));
                if (meta.response_source) log(`Response source: ${meta.response_source}`);
              }
              continue;
            }
            if (part.startsWith("event: error")) {
              const dataLine = part.split("\\n").find((l) => l.startsWith("data: "));
              if (dataLine) {
                log(`Error: ${dataLine.replace("data: ", "")}`);
              }
              continue;
            }
            if (part.startsWith("event: end")) {
              continue;
            }
            const dataLine = part.split("\\n").find((l) => l.startsWith("data: "));
            if (!dataLine) continue;
            const chunk = dataLine.replace("data: ", "");
            if (!firstChunkAt) {
              firstChunkAt = performance.now();
              log(`Client TTFT: ${Math.round(firstChunkAt - start)} ms`);
              thinkingEl.style.display = "none";
              clearTimeout(thinkingTimer);
            }
            fullText += chunk;
            streamingBubble.textContent = fullText;
            chatEl.scrollTop = chatEl.scrollHeight;
          }
        }

        if (fullText) {
          messages.push({ role: "assistant", content: fullText });
          streamingBubble.innerHTML = renderMarkdown(fullText);
        }
      });

      messageInputEl.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
          e.preventDefault();
          document.getElementById("sendBtn").click();
        }
      });

      document.getElementById("resetBtn").addEventListener("click", () => {
        messages = [];
        renderChat();
      });

      function renderChat() {
        chatEl.innerHTML = "";
        messages.forEach((m) => {
          if (m.role === "assistant") {
            appendBubble("assistant", m.content, true);
          } else {
            appendBubble("user", m.content, false);
          }
        });
      }

      const params = new URLSearchParams(window.location.search);
      const reqParam = params.get("request_id");
      const channelParam = params.get("channel_id");
      reqIdEl.value = reqParam || uuid();
      if (channelParam) channelIdEl.value = channelParam;
      payloadEl.value = JSON.stringify({
        conversation_id: conversationIdEl.value || "ui-1",
        user_id: userIdEl.value || "USR-00397",
        session_id: sessionIdEl.value || "s1",
        order_id: orderIdEl.value || "N-20260314-ITIKF",
        message: "",
        messages: []
      }, null, 2);
    </script>
  </body>
</html>
"""
    return HTMLResponse(content=html)


@router.post("/support", response_model=ConversationResponse)
@profile_api
async def support_query(turn: ConversationTurn, request: Request):
    logger = getattr(request.state, "logger", get_logger())
    logger.info("support_query.received", conversation_id=turn.conversation_id, user_id=turn.user_id, session_id=turn.session_id)

    tracer = get_tracer()
    async with tracer.trace("support_query"):
        try:
            result = await conversation_service.process_conversation(
                conversation_id=turn.conversation_id,
                user_id=turn.user_id,
                session_id=turn.session_id,
                message=turn.message,
                messages=turn.messages,
                order_id=turn.order_id,
                product_id=turn.product_id,
                payload=turn.payload,
                execution_budget_ms=turn.execution_budget_ms,
            )
        except Exception as exc:
            logger.error("support_query.failed", error=str(exc))
            raise HTTPException(status_code=500, detail=f"Agent error: {exc}")

    logger.info("support_query.completed", next_node=result.get("next_node", ""), escalation_required=result.get("escalation_required", False))
    return ConversationResponse(
        conversation_id=result.get("conversation_id", turn.conversation_id),
        user_id=result.get("user_id", turn.user_id),
        session_id=result.get("session_id", turn.session_id),
        final_response=result.get("final_response", ""),
        next_node=result.get("next_node", ""),
        escalation_required=result.get("escalation_required", False),
        tool_results=result.get("tool_results", {}),
        trace_id=result.get("trace_id", ""),
        response_source=result.get("response_source", ""),
        timings_ms=result.get("timings_ms", {}),
        emotion=result.get("emotion"),
        escalation_packet=result.get("escalation_packet"),
    )


@router.post("/support/stream")
@profile_api
async def support_query_stream(turn: ConversationTurn, request: Request):
    logger = getattr(request.state, "logger", get_logger())
    logger.info("support_query.received", conversation_id=turn.conversation_id, user_id=turn.user_id, session_id=turn.session_id)

    tracer = get_tracer()

    async def event_stream():
        start = time.perf_counter()

        # Register a queue so generate_response_node can push tokens as they arrive
        token_queue: asyncio.Queue = asyncio.Queue()
        register_token_queue(turn.conversation_id, token_queue)

        # Run the full pipeline in the background; tokens arrive via the queue
        async def run_pipeline():
            async with tracer.trace("support_query"):
                return await conversation_service.process_conversation(
                    conversation_id=turn.conversation_id,
                    user_id=turn.user_id,
                    session_id=turn.session_id,
                    message=turn.message,
                    messages=turn.messages,
                    order_id=turn.order_id,
                    product_id=turn.product_id,
                    payload=turn.payload,
                    execution_budget_ms=turn.execution_budget_ms,
                )

        graph_task = asyncio.create_task(run_pipeline())

        first_token_ms: Optional[float] = None
        try:
            # Drain the token queue until the None sentinel arrives.
            # Timeout is 15 s — all bypass paths (cache, param-request, unsupported)
            # now signal the queue immediately, so a timeout only fires on genuine
            # LLM hangs, not routing shortcuts.
            while True:
                try:
                    token = await asyncio.wait_for(token_queue.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    logger.warning("support_query.stream_timeout",
                                   elapsed_s=round(time.perf_counter() - start, 1))
                    # Safety net: if graph finished, grab final_response and push it
                    if graph_task.done():
                        try:
                            _state = graph_task.result()
                            fallback = _state.get("final_response", "")
                            if fallback:
                                yield f"data: {fallback}\n\n"
                        except Exception:
                            pass
                    break
                if token is None:
                    break
                # Progress messages are prefixed with __progress__: — send as a
                # separate SSE event type so the UI can render them as status indicators
                # rather than appending to the chat bubble.
                if isinstance(token, str) and token.startswith("__progress__:"):
                    progress_text = token[len("__progress__:"):]
                    yield f"event: progress\ndata: {json.dumps({'message': progress_text})}\n\n"
                    continue
                if first_token_ms is None:
                    first_token_ms = (time.perf_counter() - start) * 1000
                    logger.info("support_query.ttft", ttft_ms=round(first_token_ms, 1))
                yield f"data: {token}\n\n"

            # Ensure graph has fully finished (it should be, sentinel was sent last)
            result = await graph_task

        except Exception as exc:
            logger.error("support_query.failed", error=str(exc))
            yield f"event: error\ndata: {json.dumps({'error': str(exc)})}\n\n"
            graph_task.cancel()
            return
        finally:
            deregister_token_queue(turn.conversation_id)

        total_ms = (time.perf_counter() - start) * 1000
        meta = {
            "conversation_id": result.get("conversation_id", turn.conversation_id),
            "trace_id": result.get("trace_id", ""),
            "response_source": result.get("response_source", ""),
            "timings_ms": result.get("timings_ms", {}),
            "server_ttft_ms": first_token_ms or total_ms,
        }
        yield f"event: meta\ndata: {json.dumps(meta)}\n\n"
        yield "event: end\ndata: {}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
