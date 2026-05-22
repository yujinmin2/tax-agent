"""
조세심판원 결정례 수집기 (tt.go.kr)
최근 10년, 주요 세목: 법인세, 소득세, 양도소득세, 상속증여세, 부가가치세, 종합부동산세
python fetch_cases.py
→ case_texts/ 폴더에 세목별 JSON 저장
"""
import asyncio
import json
import re
import sys
import io
import time
from pathlib import Path
from playwright.async_api import async_playwright

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

OUTPUT_DIR = Path(__file__).parent / "case_texts"
CUTOFF_YEAR = 2016  # 2016년 이전은 제외 (최근 10년)

TARGET_SEMOK = {
    "11": "법인세",
    "12": "소득세",
    "20": "양도소득세",
    "40": "상속증여세",
    "50": "부가가치세",
    "90": "종합부동산세",
}

EXTRACT_JS = """
() => {
    const items = document.querySelectorAll('li.result-box');
    return Array.from(items).map(li => {
        const label = li.querySelector('.label-tax');
        const link  = li.querySelector('.result-tit a');
        const date  = li.querySelector('.date');
        const cnum  = li.querySelector('.case-num');
        return {
            semok:    label ? label.innerText.trim() : '',
            summary:  link  ? link.innerText.trim()  : '',
            date:     date  ? date.innerText.replace(/[^0-9\-]/g,'').trim() : '',
            case_num: cnum  ? cnum.innerText.replace(/\s+/g,' ').trim() : '',
        };
    });
}
"""


async def scrape_semok(page, semok_code: str, semok_name: str) -> list[dict]:
    cases = []
    page_num = 1
    stop = False

    while not stop:
        url = f"https://www.tt.go.kr/mUser/dem/demList.do?semok={semok_code}&pageNumber={page_num}"
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(1500)
        except Exception as e:
            print(f"    페이지 오류 p{page_num}: {e}")
            break

        items = await page.evaluate(EXTRACT_JS)

        if not items:
            break

        for item in items:
            date_str = item.get("date", "")
            m = re.search(r"(\d{4})-\d{2}-\d{2}", date_str)
            year = int(m.group(1)) if m else 9999

            if year < CUTOFF_YEAR:
                stop = True
                break

            summary = item.get("summary", "").strip()
            case_num = item.get("case_num", "").replace("사건번호", "").strip()
            if not summary:
                continue

            cases.append({
                "semok": semok_name,
                "case_num": case_num,
                "date": date_str,
                "text": f"[조세심판 {semok_name} {case_num} ({date_str})]\n{summary}",
            })

        total = len(cases)
        print(f"    p{page_num}: +{len(items)}건 | 누계 {total}건 (최신: {items[0].get('date','?') if items else '-'})", flush=True)

        page_num += 1
        await asyncio.sleep(0.3)  # 과부하 방지

    return cases


async def main():
    OUTPUT_DIR.mkdir(exist_ok=True)
    all_cases = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = await context.new_page()

        for code, name in TARGET_SEMOK.items():
            print(f"\n[{name}] semok={code} 수집 중...")
            cases = await scrape_semok(page, code, name)
            all_cases.extend(cases)

            # 세목별 개별 저장
            out = OUTPUT_DIR / f"{name}_cases.json"
            with open(out, "w", encoding="utf-8") as f:
                json.dump(cases, f, ensure_ascii=False, separators=(",", ":"))
            print(f"  → {name}: {len(cases)}건 저장 ({out.stat().st_size/1024:.0f} KB)")

        await browser.close()

    # 전체 합본
    out_all = OUTPUT_DIR / "all_cases.json"
    with open(out_all, "w", encoding="utf-8") as f:
        json.dump(all_cases, f, ensure_ascii=False, separators=(",", ":"))

    print(f"\n완료: 총 {len(all_cases)}건 → {out_all.name} ({out_all.stat().st_size/1024/1024:.1f} MB)")


if __name__ == "__main__":
    asyncio.run(main())
