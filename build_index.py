"""
법령 조문 분할 + BM25 + Voyage AI 임베딩 인덱스 생성
1회 실행: python build_index.py
→ law_chunks.json, law_embeddings.npy 생성 (GitHub에 커밋)
"""
import os
import re
import json
import numpy as np
from pathlib import Path

ROOT = Path(__file__).parent

LAW_FILES = [
    "국세기본법_clean.txt",
    "소득세법_clean.txt",
    "법인세법_clean.txt",
    "부가가치세법_clean.txt",
    "상속세및증여세법_clean.txt",
    "조세특례제한법_clean.txt",
    "종합부동산세법_clean.txt",
    "국세기본법시행령_clean.txt",
    "소득세법시행령_clean.txt",
    "법인세법시행령_clean.txt",
    "부가가치세법시행령_clean.txt",
    "상속세및증여세법시행령_clean.txt",
    "조세특례제한법시행령_clean.txt",
    "종합부동산세법시행령_clean.txt",
    "소득세법시행규칙_clean.txt",
    "법인세법시행규칙_clean.txt",
    "부가가치세법시행규칙_clean.txt",
    "상속세및증여세법시행규칙_clean.txt",
    "조세특례제한법시행규칙_clean.txt",
]


def split_articles(text: str, law_name: str) -> list[dict]:
    parts = re.split(r'(?=제\d+조(?:의\d+)?(?:[\s(]))', text)
    chunks = []
    for part in parts:
        part = part.strip()
        if not part or len(part) < 30:
            continue
        m = re.match(r'(제\d+조(?:의\d+)?(?:\s*\([^)]{1,50}\))?)', part)
        article_id = m.group(1).strip() if m else "전문"
        if len(part) > 2000:
            part = part[:2000]
        chunks.append({"law": law_name, "article": article_id, "text": part})
    return chunks


def main():
    voyage_key = os.environ.get("VOYAGE_API_KEY", "")
    if not voyage_key:
        print("VOYAGE_API_KEY 환경변수 없음 → BM25 인덱스만 생성")

    # 1) 조문 분할
    all_chunks = []
    for fname in LAW_FILES:
        path = ROOT / fname
        if not path.exists():
            print(f"  SKIP: {fname}")
            continue
        law_name = fname.replace("_clean.txt", "")
        text = path.read_text(encoding="utf-8")
        chunks = split_articles(text, law_name)
        all_chunks.extend(chunks)
        print(f"  {law_name}: {len(chunks)}개 조문")

    out = ROOT / "law_chunks.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(all_chunks, f, ensure_ascii=False, separators=(",", ":"))
    print(f"\nlaw_chunks.json: {len(all_chunks)}개 조문 ({out.stat().st_size/1024/1024:.1f} MB)")

    # 2) Voyage AI 임베딩
    if not voyage_key:
        print("임베딩 생략 (키 없음)")
        return

    import voyageai
    vo = voyageai.Client(api_key=voyage_key)

    texts = [c["text"] for c in all_chunks]
    batch_size = 128
    all_embeddings = []

    import time
    print(f"\nVoyage AI 임베딩 시작 ({len(texts)}개, batch={batch_size})...")
    for i in range(0, len(texts), batch_size):
        batch = texts[i: i + batch_size]
        for attempt in range(5):
            try:
                result = vo.embed(batch, model="voyage-3-lite", input_type="document")
                all_embeddings.extend(result.embeddings)
                break
            except Exception as e:
                wait = 20 * (attempt + 1)
                print(f"  오류 (재시도 {attempt+1}/5, {wait}초 대기): {e}")
                time.sleep(wait)
        else:
            raise RuntimeError(f"배치 {i} 실패 — API 키/결제 확인 필요")
        done = min(i + batch_size, len(texts))
        print(f"  {done}/{len(texts)} ({done*100//len(texts)}%)")
        time.sleep(0.3)  # 속도 제한 여유

    emb_array = np.array(all_embeddings, dtype=np.float32)
    emb_out = ROOT / "law_embeddings.npy"
    np.save(emb_out, emb_array)
    print(f"\nlaw_embeddings.npy: shape={emb_array.shape} ({emb_out.stat().st_size/1024/1024:.1f} MB)")
    print("\n완료!")


if __name__ == "__main__":
    main()
