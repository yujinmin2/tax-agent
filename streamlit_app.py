"""
세무사 에이전트 A — 웹 버전 (RAG)
Streamlit Cloud 배포용
"""

import base64
import io
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


# ── 파일 처리 ─────────────────────────────────────
def process_file(uploaded_file) -> dict | None:
    """업로드된 파일을 Anthropic content block으로 변환"""
    name = uploaded_file.name.lower()
    raw = uploaded_file.read()

    # PDF
    if name.endswith(".pdf"):
        b64 = base64.standard_b64encode(raw).decode()
        return {
            "type": "document",
            "source": {"type": "base64", "media_type": "application/pdf", "data": b64},
        }

    # 이미지
    if name.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")):
        if name.endswith(".png"):
            mime = "image/png"
        elif name.endswith((".jpg", ".jpeg")):
            mime = "image/jpeg"
        elif name.endswith(".webp"):
            mime = "image/webp"
        else:
            mime = "image/gif"
        b64 = base64.standard_b64encode(raw).decode()
        return {"type": "image", "source": {"type": "base64", "media_type": mime, "data": b64}}

    # Excel
    if name.endswith((".xlsx", ".xls")):
        try:
            import openpyxl
            wb = openpyxl.load_workbook(io.BytesIO(raw), data_only=True)
            lines = []
            for sheet in wb.sheetnames:
                ws = wb[sheet]
                lines.append(f"[시트: {sheet}]")
                for row in ws.iter_rows(values_only=True):
                    row_str = "\t".join("" if v is None else str(v) for v in row)
                    if row_str.strip():
                        lines.append(row_str)
            text = "\n".join(lines)
        except Exception as e:
            text = f"Excel 파일 파싱 오류: {e}"
        return {"type": "text", "text": f"[첨부 Excel: {uploaded_file.name}]\n{text}"}

    # CSV
    if name.endswith(".csv"):
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = raw.decode("cp949", errors="replace")
        return {"type": "text", "text": f"[첨부 CSV: {uploaded_file.name}]\n{text}"}

    return None


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

    # ── 파일 첨부 ────────────────────────────────
    st.subheader("📎 파일 첨부")
    uploaded_file = st.file_uploader(
        "PDF · 이미지 · Excel · CSV",
        type=["pdf", "png", "jpg", "jpeg", "webp", "gif", "xlsx", "xls", "csv"],
        help="세금계산서, 재무제표, 사업계획서 등을 첨부하면 AI가 함께 분석합니다.",
    )
    if uploaded_file:
        st.caption(f"✅ {uploaded_file.name} ({uploaded_file.size/1024:.1f} KB)")

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
        content = msg["content"]
        if isinstance(content, str):
            st.markdown(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        st.markdown(block["text"])
                    elif block.get("type") == "image":
                        mime = block["source"]["media_type"]
                        img_data = base64.b64decode(block["source"]["data"])
                        st.image(img_data)
                    elif block.get("type") == "document":
                        st.caption("📄 PDF 문서 첨부됨")
                else:
                    st.markdown(str(block))


# ── 입력 처리 ──────────────────────────────────────
if prompt := st.chat_input("세금 관련 질문을 입력하세요..."):
    # 파일 첨부 여부에 따라 content 구성
    if uploaded_file is not None:
        uploaded_file.seek(0)  # 파일 포인터 초기화
        file_block = process_file(uploaded_file)
        if file_block:
            user_content = [
                file_block,
                {"type": "text", "text": prompt},
            ]
        else:
            st.warning(f"지원하지 않는 파일 형식입니다: {uploaded_file.name}")
            user_content = prompt
    else:
        user_content = prompt

    st.session_state.messages.append({"role": "user", "content": user_content})
    with st.chat_message("user", avatar="👤"):
        if uploaded_file and isinstance(user_content, list):
            name = uploaded_file.name.lower()
            if name.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")):
                for blk in user_content:
                    if blk["type"] == "image":
                        st.image(base64.b64decode(blk["source"]["data"]))
            elif name.endswith(".pdf"):
                st.caption(f"📄 {uploaded_file.name}")
            elif name.endswith((".xlsx", ".xls", ".csv")):
                st.caption(f"📊 {uploaded_file.name}")
        st.markdown(prompt)

    with st.chat_message("assistant", avatar="🏛️"):
        status_placeholder = st.empty()
        response_placeholder = st.empty()
        status_placeholder.markdown("*⏳ 관련 조문 검색 중...*")

        # ── RAG: 관련 조문 검색 ─────────────────────
        # 대화 마지막 3턴 + 현재 질문으로 검색 (문맥 반영)
        def _extract_text(content):
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                return " ".join(
                    b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"
                )
            return ""

        recent_ctx = " ".join(
            _extract_text(m["content"]) for m in st.session_state.messages[-6:]
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
