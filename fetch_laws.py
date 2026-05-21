"""
국세법령정보시스템 조문 수집기
Playwright로 JavaScript 렌더링 후 법령 원문 추출
"""

import asyncio
import re
import sys
import io
from pathlib import Path
from playwright.async_api import async_playwright

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# 수집할 법령 목록 (법령명: law.go.kr URL)
LAWS = {
    # ── 법률 원문 ──────────────────────────
    "국세기본법":           "https://www.law.go.kr/법령/국세기본법",
    "소득세법":             "https://www.law.go.kr/법령/소득세법",
    "법인세법":             "https://www.law.go.kr/법령/법인세법",
    "부가가치세법":         "https://www.law.go.kr/법령/부가가치세법",
    "상속세및증여세법":     "https://www.law.go.kr/법령/상속세및증여세법",
    "조세특례제한법":       "https://www.law.go.kr/법령/조세특례제한법",
    "종합부동산세법":       "https://www.law.go.kr/법령/종합부동산세법",
    # ── 시행령 ─────────────────────────────
    "국세기본법시행령":         "https://www.law.go.kr/법령/국세기본법시행령",
    "소득세법시행령":           "https://www.law.go.kr/법령/소득세법시행령",
    "법인세법시행령":           "https://www.law.go.kr/법령/법인세법시행령",
    "부가가치세법시행령":       "https://www.law.go.kr/법령/부가가치세법시행령",
    "상속세및증여세법시행령":   "https://www.law.go.kr/법령/상속세및증여세법시행령",
    "조세특례제한법시행령":     "https://www.law.go.kr/법령/조세특례제한법시행령",
    "종합부동산세법시행령":     "https://www.law.go.kr/법령/종합부동산세법시행령",
    # ── 시행규칙 ───────────────────────────
    "소득세법시행규칙":         "https://www.law.go.kr/법령/소득세법시행규칙",
    "법인세법시행규칙":         "https://www.law.go.kr/법령/법인세법시행규칙",
    "부가가치세법시행규칙":     "https://www.law.go.kr/법령/부가가치세법시행규칙",
    "상속세및증여세법시행규칙": "https://www.law.go.kr/법령/상속세및증여세법시행규칙",
    "조세특례제한법시행규칙":   "https://www.law.go.kr/법령/조세특례제한법시행규칙",
}

OUTPUT_DIR = Path(__file__).parent / "law_texts"


async def fetch_law(page, law_name: str, url: str) -> str:
    print(f"  [{law_name}] 접속 중...")
    await page.goto(url, wait_until="domcontentloaded", timeout=60000)
    await page.wait_for_timeout(3000)

    # iframe src에서 실제 법령 URL 추출
    iframe_src = await page.eval_on_selector(
        "iframe#lawService",
        "el => el.src"
    )
    print(f"  [{law_name}] iframe URL: {iframe_src}")

    # iframe 내용 직접 접근
    base_url = "https://www.law.go.kr"
    if iframe_src.startswith("/"):
        iframe_url = base_url + iframe_src
    else:
        iframe_url = iframe_src

    await page.goto(iframe_url, wait_until="networkidle", timeout=60000)
    await page.wait_for_timeout(5000)

    # 전체 조문 버튼 클릭 시도
    for btn_text in ["전체조문", "전체 조문", "조문전체"]:
        try:
            btn = page.locator(f"text={btn_text}")
            if await btn.count() > 0:
                await btn.first.click()
                await page.wait_for_timeout(4000)
                print(f"  [{law_name}] '{btn_text}' 클릭")
                break
        except Exception:
            pass

    # 조문 내용 추출
    text = ""
    for sel in ["#lawMain", ".law-body", "#artWrap", ".cont_law", "#viewLaw", "body"]:
        try:
            el = page.locator(sel)
            if await el.count() > 0:
                t = await el.first.inner_text()
                if len(t) > 1000:
                    text = t
                    print(f"  [{law_name}] '{sel}' 에서 {len(t):,}자 추출")
                    break
        except Exception:
            continue

    if not text:
        html = await page.content()
        html_path = OUTPUT_DIR / f"{law_name}_debug2.html"
        html_path.write_text(html, encoding="utf-8")
        print(f"  [{law_name}] 추출 실패 - HTML 저장됨")

    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'[ \t]+', ' ', text)
    print(f"  [{law_name}] 최종 {len(text):,}자")
    return text


async def main():
    OUTPUT_DIR.mkdir(exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = await context.new_page()

        results = {}
        for law_name, url in LAWS.items():
            try:
                text = await fetch_law(page, law_name, url)
                results[law_name] = text

                # 개별 파일로 저장
                out_path = OUTPUT_DIR / f"{law_name}.txt"
                out_path.write_text(text, encoding="utf-8")
                print(f"  → 저장: {out_path}")

            except Exception as e:
                print(f"  [{law_name}] 오류: {e}")
                results[law_name] = ""

        await browser.close()

    # 전체 합본 저장
    all_text = ""
    for law_name, text in results.items():
        if text:
            all_text += f"\n\n{'='*60}\n{law_name}\n{'='*60}\n{text}"

    combined_path = OUTPUT_DIR / "전체법령합본.txt"
    combined_path.write_text(all_text, encoding="utf-8")
    print(f"\n[완료] 전체 합본: {combined_path}")
    print(f"   총 {len(all_text):,}자 수집됨")


if __name__ == "__main__":
    asyncio.run(main())
