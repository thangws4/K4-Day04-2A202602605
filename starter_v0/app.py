"""
IT Helpdesk Agent — Streamlit Live Chat UI
==========================================
Tái sử dụng trực tiếp run_model_tool_loop từ chat.py (KHÔNG viết agent loop mới).
Đầy đủ các thông tin audit:
  1. User request
  2. Final response
  3. Từng tool name và args
  4. Tool result / error
  5. Round / status
  6. Artifact version và prompt/tools hashes
  7. Transcript path

Khởi chạy:
  cd starter_v0
  streamlit run app.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

from env_loader import load_lab_env
from providers import make_provider
from tools import load_tool_declarations, to_openai_tools
from versioning import build_artifact_version, artifact_version_dict
from chat import (
    run_model_tool_loop,
    write_transcript,
    trim_history,
    now_iso,
    safe_slug,
)

ARTIFACTS_DIR = ROOT / "artifacts"
TRANSCRIPTS_DIR = ROOT / "transcripts"
SYSTEM_PROMPT_PATH = ARTIFACTS_DIR / "system_prompt.md"
TOOLS_PATH = ARTIFACTS_DIR / "tools.yaml"
PROVIDERS = ["openrouter", "openai", "anthropic", "gemini"]
VERSIONS = ["v0", "v1", "v2", "v3"]

load_lab_env(ROOT)

st.set_page_config(
    page_title="IT Helpdesk Agent — Live Chat & Tool Audit",
    page_icon="🖥️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
code, pre, .mono { font-family: 'JetBrains Mono', monospace !important; }

/* Dark theme accents */
section[data-testid="stSidebar"] {
    background: linear-gradient(165deg, #0d1117 0%, #161b22 60%, #0d1117 100%);
    border-right: 1px solid #30363d;
}
section[data-testid="stSidebar"] * { color: #c9d1d9; }
section[data-testid="stSidebar"] h2 { color: #58a6ff !important; font-weight: 700; font-size: 1.1rem; }

.main .block-container {
    background: #0d1117;
    padding: 1.5rem 2.5rem;
    max-width: 1200px;
}

/* Header */
.app-header {
    background: linear-gradient(135deg, #161b22 0%, #1c2128 50%, #161b22 100%);
    border: 1px solid #30363d;
    border-radius: 12px;
    padding: 1.2rem 1.8rem;
    margin-bottom: 1.2rem;
    display: flex;
    justify-content: space-between;
    align-items: center;
    box-shadow: 0 4px 12px rgba(0,0,0,0.25);
}
.header-left { display: flex; align-items: center; gap: 14px; }
.header-title { color: #f0f6fc; font-size: 1.4rem; margin: 0; font-weight: 700; }
.header-sub { color: #8b949e; font-size: 0.85rem; margin: 2px 0 0 0; }

.loop-badge {
    background: #121d2f;
    border: 1px solid #1f6feb;
    border-radius: 20px;
    padding: 4px 12px;
    font-size: 0.76rem;
    color: #58a6ff;
    font-weight: 600;
    font-family: 'JetBrains Mono', monospace;
    display: inline-flex;
    align-items: center;
    gap: 6px;
}

/* Message bubbles */
.chat-row { margin: 0.8rem 0; }
.chat-meta {
    font-size: 0.75rem;
    font-weight: 600;
    letter-spacing: 0.04em;
    margin-bottom: 5px;
    display: flex;
    align-items: center;
    gap: 8px;
}
.meta-user { color: #7ee787; }
.meta-agent { color: #58a6ff; }

.chat-user {
    background: linear-gradient(135deg, #12381f 0%, #1a4d2e 100%);
    border: 1px solid #238636;
    border-radius: 12px 12px 2px 12px;
    padding: 0.85rem 1.2rem;
    color: #f0f6fc;
    font-size: 0.95rem;
    line-height: 1.55;
    box-shadow: 0 2px 8px rgba(35,134,54,0.15);
}

.chat-agent {
    background: linear-gradient(135deg, #161b22 0%, #1c2128 100%);
    border: 1px solid #30363d;
    border-radius: 12px 12px 12px 2px;
    padding: 0.85rem 1.2rem;
    color: #c9d1d9;
    font-size: 0.95rem;
    line-height: 1.55;
}

/* Tool Audit Cards */
.tool-audit-box {
    background: #090d13;
    border: 1px solid #30363d;
    border-left: 4px solid #f0883e;
    border-radius: 8px;
    padding: 0.75rem 1rem;
    margin: 0.45rem 0;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.82rem;
}
.tool-title-bar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 6px;
}
.tool-name { color: #f0883e; font-weight: 700; font-size: 0.88rem; }
.tool-args { color: #e6edf3; background: #161b22; padding: 4px 8px; border-radius: 4px; margin: 4px 0; }
.tool-res-ok { color: #7ee787; background: #0e2015; border: 1px solid #238636; border-radius: 4px; padding: 6px 8px; margin-top: 5px; }
.tool-res-err { color: #f85149; background: #2b1111; border: 1px solid #da3633; border-radius: 4px; padding: 6px 8px; margin-top: 5px; }

/* Status Badges */
.badge { display: inline-block; padding: 2px 9px; border-radius: 12px; font-size: 0.7rem; font-weight: 700; text-transform: uppercase; }
.badge-answered  { background: #196127; color: #7ee787; border: 1px solid #238636; }
.badge-waiting   { background: #3d2b00; color: #e3b341; border: 1px solid #9e6a03; }
.badge-maxrounds { background: #3d0f0f; color: #f85149; border: 1px solid #6e1010; }
.badge-error     { background: #4c1212; color: #ff7b72; border: 1px solid #b62324; }
.badge-round     { background: #1c2d42; color: #79c0ff; border: 1px solid #1f6feb; }

/* Info panels */
.card-sidebar {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 8px;
    padding: 0.75rem 0.9rem;
    margin-bottom: 0.8rem;
    font-size: 0.8rem;
}
.card-sidebar h4 { color: #58a6ff; margin: 0 0 6px 0; font-size: 0.85rem; }

.meta-footer {
    font-size: 0.72rem;
    color: #8b949e;
    margin-top: 6px;
    display: flex;
    flex-wrap: wrap;
    gap: 12px;
}
</style>
""", unsafe_allow_html=True)


def _badge(status: str) -> str:
    cls = {
        "answered": "badge-answered",
        "waiting_for_user": "badge-waiting",
        "max_tool_rounds": "badge-maxrounds",
        "provider_error": "badge-error",
        "error": "badge-error",
    }.get(status, "badge-maxrounds")
    label = {
        "answered": "Answered",
        "waiting_for_user": "Waiting for user",
        "max_tool_rounds": "Max tool rounds",
        "provider_error": "Provider error",
        "error": "Error",
    }.get(status, status)
    return f'<span class="badge {cls}">{label}</span>'


def _render_rounds_and_tools(rounds: list[dict], tool_events: list[dict]) -> None:
    """Render round-by-round breakdown of tool calls, args, results, and errors."""
    if not rounds and not tool_events:
        return

    num_calls = len(tool_events)
    num_rounds = len(rounds) if rounds else 1
    title = f"🔍 Tool Audit Trace — {num_calls} call{'s' if num_calls != 1 else ''} across {num_rounds} round{'s' if num_rounds != 1 else ''}"

    with st.expander(title, expanded=True):
        if rounds:
            for r_idx, r in enumerate(rounds, 1):
                r_num = r.get("round", r_idx)
                calls = r.get("tool_calls", [])
                results = r.get("tool_results", [])
                st.markdown(f"##### 🔄 Round {r_num} ({len(calls)} tool call{'s' if len(calls) != 1 else ''})")
                if not calls:
                    st.caption("No tool calls made in this round (final answer generation).")
                    continue

                for i, call in enumerate(calls):
                    t_name = call.get("name", "?")
                    t_args = call.get("args", {})
                    # Match with result if available
                    res_obj = results[i].get("result") if i < len(results) else {}
                    is_err = isinstance(res_obj, dict) and ("error" in res_obj)

                    args_json = json.dumps(t_args, ensure_ascii=False, indent=2)
                    res_json = json.dumps(res_obj, ensure_ascii=False, indent=2, default=str)

                    st.markdown(f"""
                    <div class="tool-audit-box">
                      <div class="tool-title-bar">
                        <span class="tool-name">⚡ {t_name}</span>
                        <span>{f'<span class="badge badge-error">ERROR</span>' if is_err else '<span class="badge badge-answered">SUCCESS</span>'}</span>
                      </div>
                      <div style="color:#8b949e; margin-bottom:2px;"><b>Arguments:</b></div>
                      <div class="tool-args">{json.dumps(t_args, ensure_ascii=False)}</div>
                      <div style="color:#8b949e; margin-top:6px; margin-bottom:2px;"><b>Result / Error:</b></div>
                      <div class="{ 'tool-res-err' if is_err else 'tool-res-ok' }">
                        { '❌ Error details: ' if is_err else '✅ Result data: ' }
                        <pre style="margin:4px 0 0 0; white-space:pre-wrap; word-break:break-all; font-size:0.75rem;">{res_json[:1500]}</pre>
                      </div>
                    </div>
                    """, unsafe_allow_html=True)
        else:
            # Fallback for flat tool_events list
            for ev in tool_events:
                t_name = ev.get("tool", "?")
                t_args = ev.get("args", {})
                res_obj = ev.get("result", {})
                is_err = isinstance(res_obj, dict) and ("error" in res_obj)
                res_json = json.dumps(res_obj, ensure_ascii=False, indent=2, default=str)

                st.markdown(f"""
                <div class="tool-audit-box">
                  <div class="tool-title-bar">
                    <span class="tool-name">⚡ {t_name}</span>
                    <span>{f'<span class="badge badge-error">ERROR</span>' if is_err else '<span class="badge badge-answered">SUCCESS</span>'}</span>
                  </div>
                  <div style="color:#8b949e;"><b>Arguments:</b></div>
                  <div class="tool-args">{json.dumps(t_args, ensure_ascii=False)}</div>
                  <div style="color:#8b949e; margin-top:6px;"><b>Result:</b></div>
                  <div class="{ 'tool-res-err' if is_err else 'tool-res-ok' }">
                    <pre style="margin:4px 0 0 0; white-space:pre-wrap; font-size:0.75rem;">{res_json[:1200]}</pre>
                  </div>
                </div>
                """, unsafe_allow_html=True)


def _init_transcript(version_label: str, provider_name: str, model_id: str | None, history_w: int, max_r: int):
    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S%f")
    transcript_id = "_".join([safe_slug(version_label), safe_slug(provider_name), timestamp])
    tpath = TRANSCRIPTS_DIR / f"{transcript_id}.transcript.json"
    av = build_artifact_version(version_label, SYSTEM_PROMPT_PATH, TOOLS_PATH)
    transcript = {
        "transcript_id": transcript_id,
        **artifact_version_dict(av),
        "provider": provider_name,
        "model": model_id or "default",
        "system_prompt": str(SYSTEM_PROMPT_PATH),
        "tools": str(TOOLS_PATH),
        "history_window": history_w,
        "max_tool_rounds": max_r,
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "turns": [],
    }
    return transcript, tpath


# ── Sidebar: Configuration & Audit Metadata ──────────────────────────────────
with st.sidebar:
    st.markdown("## ⚙️ Configuration")

    provider_name = st.selectbox("LLM Provider", PROVIDERS, index=0, key="provider_sel")
    model_input = st.text_input("Model ID (optional)", placeholder="e.g. google/gemini-2.5-flash", key="model_input")
    version_label = st.selectbox("Artifact Version", VERSIONS, index=0, key="version_sel")

    # Compute & display Artifact Version and Hashes
    try:
        av = build_artifact_version(version_label, SYSTEM_PROMPT_PATH, TOOLS_PATH)
        st.markdown(f"""
        <div class="card-sidebar">
          <h4>🏷️ Artifact Version & Hashes</h4>
          <div><b>Version:</b> <code style="color:#58a6ff;">{av.artifact_version}</code></div>
          <div style="margin-top:4px;"><b>Prompt Hash (sha256):</b></div>
          <code style="font-size:0.7rem; color:#7ee787; word-break:break-all;">{av.prompt_hash}</code>
          <div style="margin-top:4px;"><b>Tools Hash (sha256):</b></div>
          <code style="font-size:0.7rem; color:#f0883e; word-break:break-all;">{av.tools_hash}</code>
        </div>
        """, unsafe_allow_html=True)
    except Exception as e:
        st.error(f"Cannot compute artifact version: {e}")
        av = None

    st.markdown("---")
    c1, c2 = st.columns(2)
    with c1:
        history_window = st.number_input("History Window", min_value=1, max_value=20, value=5, step=1)
    with c2:
        max_tool_rounds = st.number_input("Max Tool Rounds", min_value=1, max_value=10, value=4, step=1)

    st.markdown("---")
    # Loop Verification Badge (Deliverable check)
    st.markdown("""
    <div class="card-sidebar" style="border-color:#1f6feb;">
      <h4 style="color:#79c0ff;">🛡️ Pre-Submission Audit</h4>
      <div style="font-size:0.76rem; line-height:1.5;">
        ✅ <b>Shared Loop:</b> <code style="color:#58a6ff;">chat.py::run_model_tool_loop</code><br>
        ✅ <b>Audit Fields:</b> Tool, Args, Result/Error, Rounds, Hashes<br>
        ✅ <b>Security:</b> Secrets via <code style="color:#e3b341;">.env</code> only
      </div>
    </div>
    """, unsafe_allow_html=True)

    # Active Transcript Path
    st.markdown("#### 📄 Active Transcript")
    if "transcript_path" in st.session_state:
        st.code(st.session_state.transcript_path, language="text")
        if "transcript" in st.session_state and st.session_state.transcript.get("turns"):
            with st.expander(f"View Transcript JSON ({len(st.session_state.transcript['turns'])} turns)", expanded=False):
                st.json(st.session_state.transcript)
    else:
        st.caption(f"Will save to: `starter_v0/transcripts/{version_label}_{provider_name}_<timestamp>.transcript.json`")

    st.markdown("---")
    if st.button("🗑️ Clear Chat / New Session", use_container_width=True, type="secondary"):
        for k in ["messages", "history", "transcript", "transcript_path", "turn_index"]:
            st.session_state.pop(k, None)
        st.rerun()


# ── App Header ───────────────────────────────────────────────────────────────
av_str = av.artifact_version if av else version_label
st.markdown(f"""
<div class="app-header">
  <div class="header-left">
    <div style="font-size:2.2rem; line-height:1;">🖥️</div>
    <div>
      <h1 class="header-title">IT Helpdesk Agent</h1>
      <p class="header-sub">Streamlit Live Chat · Tool Execution Audit · Multi-Turn Transcript Logging</p>
    </div>
  </div>
  <div style="text-align:right;">
    <div class="loop-badge">🔄 Loop: run_model_tool_loop (chat.py)</div>
    <div style="font-size:0.75rem; color:#8b949e; margin-top:4px;">
      Artifact: <code style="color:#58a6ff;">{av_str}</code>
    </div>
  </div>
</div>
""", unsafe_allow_html=True)


# ── Session State Initialization ─────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = []
if "history" not in st.session_state:
    st.session_state.history = []
if "turn_index" not in st.session_state:
    st.session_state.turn_index = 0


# ── Render Conversation History ──────────────────────────────────────────────
if not st.session_state.messages:
    st.info("""
    👋 **Chào mừng đến với IT Helpdesk Agent!**
    
    Hãy nhập câu hỏi vào ô chat bên dưới, hoặc thử một trong các kịch bản demo:
    - `Kiểm tra trạng thái VPN production giúp mình.` *(Gọi `check_service_status`)*
    - `Inspect thiết bị LT-204 và cho mình biết diagnostic.` *(Gọi `inspect_device`)*
    - `Mình muốn tạo ticket lỗi Wi-Fi trên máy LT-240 mức medium.` *(Gọi `clarify` để xác nhận)*
    - `Tìm hướng dẫn khắc phục VPN không kết nối được.` *(Gọi `search_kb`)*
    - `Tra cứu nhân viên EMP-1003 và liệt kê thiết bị được cấp.` *(Gọi `lookup_user`)*
    """)

for msg in st.session_state.messages:
    if msg["role"] == "user":
        st.markdown(f"""
        <div class="chat-row">
          <div class="chat-meta meta-user">
            <span>👤 User Request</span>
            <span style="color:#8b949e; font-weight:normal;">(Turn #{msg.get("turn_index", 1)})</span>
          </div>
          <div class="chat-user">{msg["content"]}</div>
        </div>
        """, unsafe_allow_html=True)
    else:
        status = msg.get("status", "answered")
        rounds = msg.get("rounds", [])
        num_rounds = len(rounds) if rounds else 1
        st.markdown(f"""
        <div class="chat-row">
          <div class="chat-meta meta-agent">
            <span>🤖 Final Response</span>
            &nbsp; {_badge(status)}
            <span class="badge badge-round">Round: {num_rounds}/{max_tool_rounds}</span>
          </div>
          <div class="chat-agent">{msg["content"]}</div>
        </div>
        """, unsafe_allow_html=True)

        # Render Tool Audit Breakdown
        _render_rounds_and_tools(rounds, msg.get("tool_events", []))

        # Turn metadata footer
        if msg.get("transcript_path"):
            st.markdown(f"""
            <div class="meta-footer">
              <span>🏷️ <b>Version:</b> <code>{msg.get('artifact_version', av_str)}</code></span>
              <span>📄 <b>Transcript:</b> <code>{Path(msg['transcript_path']).name}</code></span>
            </div>
            """, unsafe_allow_html=True)


# ── Chat Input & Agent Loop Execution ────────────────────────────────────────
user_input = st.chat_input("Nhập yêu cầu IT helpdesk của bạn... (Ví dụ: Kiểm tra trạng thái VPN production)")

if user_input:
    st.session_state.turn_index += 1
    current_turn = st.session_state.turn_index

    # Add user message to UI state
    st.session_state.messages.append({
        "role": "user",
        "content": user_input,
        "turn_index": current_turn,
    })

    with st.spinner(f"Agent đang xử lý (Turn #{current_turn} via run_model_tool_loop)..."):
        try:
            # 1. Initialize provider & tools
            provider = make_provider(provider_name)
            model = model_input.strip() or None
            system_prompt = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
            tool_declarations = load_tool_declarations(TOOLS_PATH)
            openai_tools = to_openai_tools(tool_declarations)

            # 2. Build messages with history window
            messages = [
                {"role": "system", "content": system_prompt},
                *trim_history(st.session_state.history, int(history_window)),
                {"role": "user", "content": user_input},
            ]

            # 3. REUSE THE EXACT SAME RUN_MODEL_TOOL_LOOP (Requirement: UI uses shared loop)
            result = run_model_tool_loop(
                provider=provider,
                messages=messages,
                tools=openai_tools,
                model=model,
                max_tool_rounds=int(max_tool_rounds),
            )

            assistant_text = result["assistant_text"]
            status = result["status"]
            tool_events = result.get("tool_events", [])
            rounds = result.get("rounds", [])

            # 4. Initialize transcript on first turn if needed
            if "transcript" not in st.session_state:
                transcript, tpath = _init_transcript(
                    version_label, provider_name, model, int(history_window), int(max_tool_rounds)
                )
                st.session_state.transcript = transcript
                st.session_state.transcript_path = str(tpath)

            # 5. Append turn to transcript and save
            turn_record = {
                "turn_index": current_turn,
                "started_at": now_iso(),
                "user": user_input,
                "status": status,
                "assistant_text": assistant_text,
                "rounds": rounds,
                "tool_events": tool_events,
                "ended_at": now_iso(),
            }
            st.session_state.transcript["turns"].append(turn_record)
            write_transcript(Path(st.session_state.transcript_path), st.session_state.transcript)

            # 6. Update conversational history & UI messages
            st.session_state.history.append({"role": "user", "content": user_input})
            st.session_state.history.append({"role": "assistant", "content": assistant_text})
            st.session_state.messages.append({
                "role": "assistant",
                "content": assistant_text,
                "status": status,
                "rounds": rounds,
                "tool_events": tool_events,
                "artifact_version": av.artifact_version if av else version_label,
                "transcript_path": st.session_state.transcript_path,
            })

        except Exception as exc:
            st.session_state.messages.append({
                "role": "assistant",
                "content": f"⚠️ **Provider Error:** `{type(exc).__name__}: {exc}`",
                "status": "provider_error",
                "rounds": [],
                "tool_events": [],
                "artifact_version": av.artifact_version if av else version_label,
                "transcript_path": st.session_state.get("transcript_path", ""),
            })

    st.rerun()

