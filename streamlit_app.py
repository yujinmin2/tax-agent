"""
세무사 에이전트 A — 웹 버전 (RAG)
Streamlit Cloud 배포용
"""

import streamlit as st
import anthropic
from pathlib import Path
from tax_knowledge_2026 import BASE_PROMPT
from rag import LawRetriever

st.set_page_config(
    page_title="세무사 에이전트 A",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("🏛️ 세무사 에이전트 A")
st.caption("2026년 한국 세법 전문 AI · claude-opus-4-7 · Adaptive Thinking · RAG")


# ── RAG 인덱스 로드 (앱 수명 동안 1회) ─────────────
@st.cache_resource
def get_retriever():
    root = Path(__file__).parent
    chunks = root / "law_chunks.json"
    embeddings = root / "law_embeddings.npy"
    if not chunks.exists():
        st.error("law_chunks.json 없음. build_index.py 먼저 실행하세요.")
        st.stop()
    voyage_key = st.secrets.get("VOYAGE_API_KEY", "")
    return LawRetriever(chunks, embeddings, voyage_key)


@st.cache_resource
def get_client():
    return anthropic.Anthropic(api_key=st.secrets["ANTHROPIC_API_KEY"])


retriever = get_retriever()
client = get_client()


# ── 사이드바 ──────────────────────────────────────
def _empty_stats():
    return {"input": 0, "cache_read": 0, "cache_write": 0, "output": 0, "turns": 0}


with st.sidebar:
    st.header("⚙️ 메뉴")

    if st.button("🗑️ 대화 초기화", use_container_width=True):
        st.session_state.messages = []
        st.session_state.stats = _empty_stats()
        st.rerun()

    st.divider()
    st.subheader("📊 토큰 사용량")

    if "stats" in st.session_state:
        s = st.session_state.stats
        col1, col2 = st.columns(2)
        col1.metric("대화 횟수", s["turns"])
        col2.metric("출력 토큰", f"{s['output']:,}")
        st.caption(
            f"입력 {s['input']:,} | 캐시읽기 {s['cache_read']:,} | 캐시쓰기 {s['cache_write']:,}"
        )

    st.divider()
    st.markdown(
        """
**주요 기능**
- 소득세 · 법인세 · 부가가치세
- 상속·증여세 · 종합부동산세
- 양도소득세 · 원천징수
- 세무신고 절차 · 절세 전략
        """
    )


# ── 세션 초기화 ────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = []
if "stats" not in st.session_state:
    st.session_state.stats = _empty_stats()


# ── 대화 내역 출력 ─────────────────────────────────
for msg in st.session_state.messages:
    avatar = "👤" if msg["role"] == "user" else "🏛️"
    with st.chat_message(msg["role"], avatar=avatar):
        st.markdown(msg["content"])


# ── 입력 처리 ──────────────────────────────────────
if prompt := st.chat_input("세금 관련 질문을 입력하세요..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar="👤"):
        st.markdown(prompt)

    with st.chat_message("assistant", avatar="🏛️"):
        status_placeholder = st.empty()
        response_placeholder = st.empty()
        status_placeholder.markdown("*⏳ 관련 조문 검색 중...*")

        # ── RAG: 관련 조문 검색 ─────────────────────
        # 대화 마지막 3턴 + 현재 질문으로 검색 (문맥 반영)
        recent_ctx = " ".join(
            m["content"] for m in st.session_state.messages[-6:]
        )
        retrieved = retriever.retrieve(recent_ctx, top_k=25)

        # 시스템 프롬프트 구성
        system_blocks = [
            {
                "type": "text",
                "text": BASE_PROMPT,
                "cache_control": {"type": "ephemeral"},  # BASE_PROMPT는 캐싱
            }
        ]
        if retrieved:
            system_blocks.append({
                "type": "text",
                "text": (
                    "\n\n══════════════════════════════\n"
                    "【이번 질문과 관련된 실제 법령 조문 (law.go.kr 2026)】\n"
                    "아래 조문을 우선 인용하여 답변하세요.\n"
                    "══════════════════════════════\n\n"
                    + retrieved
                ),
            })

        status_placeholder.markdown("*⏳ 분석 중...*")
        full_response = ""
        started = False

        with client.messages.stream(
            model="claude-opus-4-7",
            max_tokens=8192,
            thinking={"type": "adaptive"},
            system=system_blocks,
            messages=st.session_state.messages,
        ) as stream:
            for text in stream.text_stream:
                if not started:
                    started = True
                    status_placeholder.empty()
                full_response += text
                response_placeholder.markdown(full_response + "▌")

            final_msg = stream.get_final_message()

        response_placeholder.markdown(full_response)

        # 사용량 집계
        usage = final_msg.usage
        s = st.session_state.stats
        s["input"] += getattr(usage, "input_tokens", 0) or 0
        s["cache_read"] += getattr(usage, "cache_read_input_tokens", 0) or 0
        s["cache_write"] += getattr(usage, "cache_creation_input_tokens", 0) or 0
        s["output"] += getattr(usage, "output_tokens", 0) or 0
        s["turns"] += 1

    st.session_state.messages.append({"role": "assistant", "content": full_response})
