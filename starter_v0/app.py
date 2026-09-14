"""
IT Helpdesk Agent — Streamlit chat UI
=====================================
Tái sử dụng trực tiếp run_model_tool_loop từ chat.py (KHÔNG viết agent loop mới).

- Khung chat dạng tin nhắn: user bên phải, agent bên trái; ví dụ chọn nhanh khi chưa có tin nhắn.
- Sidebar: cuộc trò chuyện mới, 5 lịch sử chat gần nhất (+ "Xem thêm"), thông số kỹ thuật
  (provider, model, version, history window, max tool rounds) và công tắc "Chi tiết kỹ thuật"
  để xem tool name, arguments, result/error, round/status, artifact version và transcript path.
- Version v0–v3 chạy đúng snapshot artifact trong artifacts/versions/<version>/ (hash khớp
  artifacts/version_log.csv).
- Lịch sử chat chính là transcript JSON trong starter_v0/transcripts/ (cùng format chat.py).
  Một transcript gắn với một cấu hình; nếu cấu hình đổi, tin nhắn tiếp theo được ghi sang
  transcript mới có `continued_from`, vẫn giữ ngữ cảnh hội thoại.

Khởi chạy:
  cd starter_v0
  streamlit run app.py
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

from chat import now_iso, run_model_tool_loop, safe_slug, trim_history, write_transcript
from env_loader import load_lab_env
from providers import make_provider
from tools import load_tool_declarations, to_openai_tools
from versioning import artifact_version_dict, build_artifact_version

TRANSCRIPTS_DIR = ROOT / "transcripts"
VERSIONS_DIR = ROOT / "artifacts" / "versions"
VERSIONS = ["v0", "v1", "v2", "v3"]

ASSISTANT_NAME = "Northstar IT Assistant"
PROVIDERS = ["gemini", "openrouter", "openai", "anthropic"]
# Team-wide eval model: gemini-3.5-flash/3.6-flash free tier only allows ~20 requests/day.
DEFAULT_MODELS = {"gemini": "gemini-3.1-flash-lite"}
HISTORY_PAGE_SIZE = 5
MAX_CHAIN_DEPTH = 20
EXAMPLES = {
    ":material/vpn_lock: Trạng thái VPN": "VPN production có đang gặp sự cố không?",
    ":material/laptop: Kiểm tra laptop": "Kiểm tra Wi-Fi trên laptop của mình giúp nhé.",
    ":material/badge: Tra cứu nhân viên": "Tra cứu tài khoản nhân viên EMP-1003 và thiết bị được cấp.",
    ":material/menu_book: Hướng dẫn Outlook": "Tìm hướng dẫn cấu hình Outlook profile trên Windows 11.",
    ":material/confirmation_number: Tạo ticket": "Tạo ticket lỗi VPN trên máy LT-204 mức high.",
}
RESUMABLE_STATUSES = {"answered", "waiting_for_user", "max_tool_rounds"}

load_lab_env(ROOT)
st.set_page_config(page_title=ASSISTANT_NAME, page_icon="🖥️")


# ── Messaging layout: user bubbles on the right, agent bubbles on the left ────
if st.context.theme.type == "dark":
    user_bg, user_fg, bot_bg, bot_border = "#2563eb", "#ffffff", "#1c2128", "#30363d"
else:
    user_bg, user_fg, bot_bg, bot_border = "#2563eb", "#ffffff", "#f1f3f6", "#e1e4e8"
st.html(f"""
<style>
[data-testid="stChatMessage"] {{ background: transparent !important; padding: 0.2rem 0; gap: 0.6rem; }}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {{ flex-direction: row-reverse; }}
[data-testid="stChatMessageContent"] {{
    flex: 0 1 auto; width: fit-content; max-width: 78%; margin: 0 !important;
    padding: 0.55rem 0.95rem; border-radius: 18px;
}}
[data-testid="stChatMessageContent"] [data-testid="stMarkdownContainer"] {{ margin-bottom: 0 !important; }}
[data-testid="stChatMessageContent"] p:last-child {{ margin-bottom: 0; }}
[aria-label="Chat message from user"] {{ background: {user_bg}; border-bottom-right-radius: 4px; }}
[aria-label="Chat message from user"] * {{ color: {user_fg}; }}
[aria-label="Chat message from assistant"] {{
    background: {bot_bg}; border: 1px solid {bot_border}; border-bottom-left-radius: 4px;
}}
.st-key-history button, .st-key-history button div {{ justify-content: flex-start; }}
.st-key-history button > div {{ width: 100%; }}
.st-key-history button p {{ white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: left; }}
</style>
""")


# ── Helpers ───────────────────────────────────────────────────────────────────
def _artifact_paths(version: str) -> tuple[Path, Path]:
    return VERSIONS_DIR / version / "system_prompt.md", VERSIONS_DIR / version / "tools.yaml"


def _md_escape(text: object) -> str:
    """Show user text literally in st.markdown (no headings, links or emphasis)."""
    escaped = re.sub(r"([\\`*_{}\[\]()#+\-.!|>~<])", r"\\\1", str(text))
    return escaped.replace("\n", "  \n")


def _reply_text(text: str | None) -> str:
    """Return `reply` from the prompt's JSON output contract, or the raw text otherwise."""
    candidate = re.sub(r"^```(?:json)?\s*|\s*```$", "", (text or "").strip())
    try:
        data = json.loads(candidate)
    except (json.JSONDecodeError, TypeError):
        return text or ""
    if isinstance(data, dict) and "reply" in data:
        return str(data["reply"])
    return text or ""


def _read_transcript(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _title_of(transcript: dict) -> str:
    if transcript.get("title"):
        return transcript["title"]
    for turn in transcript.get("turns", []):
        if turn.get("user"):
            return turn["user"].strip().splitlines()[0][:60]
    return "Cuộc trò chuyện trống"


def _normalize_model(model: object) -> str:
    return "" if model in (None, "default") else str(model)


def _config_of(transcript: dict) -> tuple:
    return (
        transcript.get("version"),
        transcript.get("provider"),
        _normalize_model(transcript.get("model")),
        transcript.get("artifact_version"),
        transcript.get("history_window"),
        transcript.get("max_tool_rounds"),
    )


def _chain(transcript: dict) -> list[dict]:
    """Oldest-first transcripts this conversation continues from, ending with itself."""
    chain = [transcript]
    for _ in range(MAX_CHAIN_DEPTH):
        parent_name = chain[-1].get("continued_from")
        parent = _read_transcript(TRANSCRIPTS_DIR / parent_name) if parent_name else None
        if parent is None:
            break
        chain.append(parent)
    return list(reversed(chain))


def _history_from(chain: list[dict]) -> list[dict[str, str]]:
    history: list[dict[str, str]] = []
    for transcript in chain:
        for turn in transcript.get("turns", []):
            if turn.get("status") in RESUMABLE_STATUSES and turn.get("assistant_text"):
                history.append({"role": "user", "content": turn["user"]})
                history.append({"role": "assistant", "content": turn["assistant_text"]})
    return history


def _list_conversations() -> list[tuple[Path, dict]]:
    if not TRANSCRIPTS_DIR.exists():
        return []
    items: list[tuple[Path, dict]] = []
    parents: set[str] = set()
    for path in TRANSCRIPTS_DIR.glob("*.transcript.json"):
        data = _read_transcript(path)
        if not data or not data.get("turns"):
            continue
        if data.get("continued_from"):
            parents.add(data["continued_from"])
        items.append((path, data))
    items = [item for item in items if item[0].name not in parents]
    items.sort(key=lambda item: item[1].get("updated_at", ""), reverse=True)
    return items


# ── Session state & callbacks ─────────────────────────────────────────────────
def _init_state() -> None:
    defaults: dict[str, Any] = {
        "provider_sel": PROVIDERS[0],
        "version_sel": VERSIONS[-1],
        "history_window": 5,
        "max_tool_rounds": 4,
        "show_details": False,
        "history_limit": HISTORY_PAGE_SIZE,
    }
    for provider in PROVIDERS:
        defaults[f"model_input_{provider}"] = DEFAULT_MODELS.get(provider, "")
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def _new_conversation() -> None:
    st.session_state.pop("transcript_path", None)


def _show_more_history() -> None:
    st.session_state.history_limit += HISTORY_PAGE_SIZE


def _pick_example() -> None:
    label = st.session_state.get("example_pick")
    if label:
        st.session_state.pending_prompt = EXAMPLES[label]
        st.session_state.example_pick = None


def _open_conversation(path: Path) -> None:
    data = _read_transcript(path)
    if data is None:
        return
    st.session_state.transcript_path = str(path)
    # Restore the conversation's own parameters so continuing it keeps the same transcript.
    if data.get("provider") in PROVIDERS:
        st.session_state.provider_sel = data["provider"]
        st.session_state[f"model_input_{data['provider']}"] = _normalize_model(data.get("model"))
    if data.get("version") in VERSIONS:
        st.session_state.version_sel = data["version"]
    for key in ("history_window", "max_tool_rounds"):
        if isinstance(data.get(key), int):
            st.session_state[key] = data[key]


def _create_transcript(config: dict, title: str, continued_from: str | None) -> tuple[dict, Path]:
    artifact = config["artifact"]
    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S%f")
    transcript_id = "_".join([safe_slug(artifact.version), safe_slug(config["provider"]), timestamp])
    transcript = {
        "transcript_id": transcript_id,
        **artifact_version_dict(artifact),
        "provider": config["provider"],
        "model": config["model"] or None,
        "system_prompt": str(config["prompt_path"]),
        "tools": str(config["tools_path"]),
        "history_window": config["history_window"],
        "max_tool_rounds": config["max_tool_rounds"],
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "title": title,
        "continued_from": continued_from,
        "turns": [],
    }
    return transcript, TRANSCRIPTS_DIR / f"{transcript_id}.transcript.json"


# ── Rendering ─────────────────────────────────────────────────────────────────
def _render_details(turn: dict, transcript: dict) -> None:
    rounds = turn.get("rounds") or []
    n_calls = sum(len(r.get("tool_calls") or []) for r in rounds)
    with st.expander(f"{n_calls} tool call · {turn.get('status', '')}", icon=":material/build:", type="compact"):
        for r in rounds:
            results = r.get("tool_results") or []
            for index, call in enumerate(r.get("tool_calls") or []):
                result = results[index].get("result") if index < len(results) else None
                is_error = isinstance(result, dict) and "error" in result
                with st.expander(f"Round {r.get('round')} · {call.get('name')}", type="step"):
                    st.json(call.get("args") or {})
                    if result is not None:
                        st.json(result, expanded=is_error)
        st.caption(f"{transcript.get('artifact_version')} · {transcript.get('transcript_id')}.transcript.json")


def _render_turn(turn: dict, transcript: dict, show_details: bool) -> None:
    with st.chat_message("user"):
        st.markdown(_md_escape(turn.get("user", "")))
    with st.chat_message("assistant"):
        if turn.get("status") == "provider_error":
            st.error("Không kết nối được model, vui lòng thử lại.", icon=":material/error:")
        else:
            st.markdown(_reply_text(turn.get("assistant_text")))
        if show_details:
            _render_details(turn, transcript)


# ── Sidebar ───────────────────────────────────────────────────────────────────
_init_state()

active_path = Path(st.session_state["transcript_path"]) if st.session_state.get("transcript_path") else None
active = _read_transcript(active_path) if active_path else None

with st.sidebar:
    st.button("Cuộc trò chuyện mới", icon=":material/edit_square:", on_click=_new_conversation, width="stretch")
    st.caption("Lịch sử")
    conversations = _list_conversations()
    with st.container(key="history", gap="xxsmall"):
        for path, data in conversations[: st.session_state.history_limit]:
            st.button(
                _title_of(data),
                key=f"conv_{path.name}",
                on_click=_open_conversation,
                args=(path,),
                type="secondary" if active_path and path.name == active_path.name else "tertiary",
                width="stretch",
            )
    if len(conversations) > st.session_state.history_limit:
        st.button("Xem thêm", icon=":material/expand_more:", key="show_more_history", on_click=_show_more_history, type="tertiary")

    st.divider()
    st.caption("Thông số kỹ thuật")
    provider_name = st.selectbox("Provider", PROVIDERS, key="provider_sel")
    model_input = st.text_input(
        "Model", key=f"model_input_{provider_name}", placeholder="Để trống = model mặc định của provider"
    )
    version_label = st.selectbox(
        "Artifact version",
        VERSIONS,
        key="version_sel",
        help="Chạy đúng system_prompt.md và tools.yaml của version này (artifacts/versions/).",
    )
    history_window = st.slider("History window", min_value=1, max_value=20, key="history_window")
    max_tool_rounds = st.slider("Max tool rounds", min_value=1, max_value=10, key="max_tool_rounds")
    show_details = st.toggle("Chi tiết kỹ thuật", key="show_details")

    prompt_path, tools_path = _artifact_paths(version_label)
    artifact = build_artifact_version(version_label, prompt_path, tools_path)
    if show_details:
        st.caption(f"`{artifact.artifact_version}`")
        if active_path:
            st.caption(f"`{active_path.name}`")

config = {
    "version": version_label,
    "provider": provider_name,
    "model": model_input.strip(),
    "artifact": artifact,
    "prompt_path": prompt_path,
    "tools_path": tools_path,
    "history_window": int(history_window),
    "max_tool_rounds": int(max_tool_rounds),
}
config_key = (
    config["version"], config["provider"], config["model"],
    artifact.artifact_version, config["history_window"], config["max_tool_rounds"],
)
# Browser tab: AI name + the model and artifact version actually answering.
st.set_page_config(page_title=f"{ASSISTANT_NAME} · {config['model'] or config['provider']} · {version_label}")


# ── Chat ──────────────────────────────────────────────────────────────────────
chain = _chain(active) if active else []
if not chain:
    st.title("Tôi có thể giúp gì cho bạn?")
    st.caption(f"{ASSISTANT_NAME} · trợ lý IT service desk của Northstar Labs · dữ liệu giả lập")
    st.pills("Ví dụ", list(EXAMPLES), key="example_pick", on_change=_pick_example, label_visibility="collapsed")
for transcript in chain:
    for turn in transcript.get("turns", []):
        _render_turn(turn, transcript, show_details)

prompt = st.chat_input("Nhập tin nhắn…", submit_mode="disable") or st.session_state.pop("pending_prompt", None)
if prompt:
    if active is None or _config_of(active) != config_key:
        continued_from = active_path.name if active and active.get("turns") else None
        title = _title_of(active) if continued_from else prompt.strip().splitlines()[0][:60]
        transcript, transcript_path = _create_transcript(config, title, continued_from)
        chain = [*chain, transcript]
    else:
        transcript, transcript_path = active, active_path

    turn: dict[str, Any] = {
        "turn_index": len(transcript["turns"]) + 1,
        "started_at": now_iso(),
        "user": prompt,
        "status": "started",
        "assistant_text": None,
        "rounds": [],
        "tool_events": [],
    }
    with st.chat_message("user"):
        st.markdown(_md_escape(prompt))
    with st.chat_message("assistant"):
        with st.spinner("Đang trả lời…"):
            try:
                messages = [
                    {"role": "system", "content": config["prompt_path"].read_text(encoding="utf-8")},
                    *trim_history(_history_from(chain), config["history_window"]),
                    {"role": "user", "content": prompt},
                ]
                # Same agent loop as chat.py (lab requirement: UI must not implement its own loop).
                turn.update(run_model_tool_loop(
                    provider=make_provider(config["provider"]),
                    messages=messages,
                    tools=to_openai_tools(load_tool_declarations(config["tools_path"])),
                    model=config["model"] or None,
                    max_tool_rounds=config["max_tool_rounds"],
                ))
            except Exception as exc:
                turn.update({"status": "provider_error", "error": f"{type(exc).__name__}: {exc}"})

    # Same transcript format as chat.py, including provider_error turns.
    turn["ended_at"] = now_iso()
    transcript["turns"].append(turn)
    write_transcript(transcript_path, transcript)
    st.session_state.transcript_path = str(transcript_path)
    st.rerun()
