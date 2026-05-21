"""
세무사 에이전트A — 2026년 한국 세법 전문 AI
대화형 CLI, 프롬프트 캐싱, 멀티턴 대화 지원
"""

import os
import sys
import io

# Windows UTF-8 출력 강제
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import anthropic
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.prompt import Prompt
from rich.text import Text
from rich import box
from tax_knowledge_2026 import SYSTEM_PROMPT

console = Console(force_terminal=True, highlight=True)

BANNER = """
==========================================================
       세무사 에이전트 A  (2026년 한국 세법)
              AI Tax Advisor Korea
==========================================================
"""

HELP_TEXT = """
[bold cyan]사용법[/bold cyan]
  • 세금 관련 질문을 자유롭게 입력하세요
  • [bold]/clear[/bold]   — 대화 초기화
  • [bold]/history[/bold] — 대화 내역 보기
  • [bold]/cache[/bold]   — 캐시 사용량 확인
  • [bold]/help[/bold]    — 도움말
  • [bold]/quit[/bold]    — 종료

[bold cyan]주요 기능[/bold cyan]
  소득세 · 법인세 · 부가가치세 · 상속·증여세
  종합부동산세 · 지방세 · 양도소득세 · 원천징수
  세무신고 절차 · 세액공제·감면 · 절세 전략 안내
"""


def get_api_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        console.print("[bold red]오류:[/] ANTHROPIC_API_KEY 환경변수가 설정되지 않았습니다.")
        console.print("설정 방법: [bold]set ANTHROPIC_API_KEY=your_api_key[/bold]")
        sys.exit(1)
    return key


def format_cache_stats(usage) -> str:
    cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
    cache_write = getattr(usage, "cache_creation_input_tokens", 0) or 0
    input_tokens = getattr(usage, "input_tokens", 0) or 0
    output_tokens = getattr(usage, "output_tokens", 0) or 0
    total_input = input_tokens + cache_read + cache_write
    return (
        f"입력 {input_tokens:,} | 캐시읽기 {cache_read:,} | "
        f"캐시쓰기 {cache_write:,} | 출력 {output_tokens:,} | 합계 {total_input:,}"
    )


class TaxAgent:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=get_api_key())
        self.messages: list[dict] = []
        self.total_cache_read = 0
        self.total_cache_write = 0
        self.total_input = 0
        self.total_output = 0
        self.turn_count = 0

    def chat(self, user_input: str) -> str:
        self.messages.append({"role": "user", "content": user_input})

        with console.status("[bold green]분석 중...[/]", spinner="dots"):
            response = self.client.messages.create(
                model="claude-opus-4-7",
                max_tokens=4096,
                thinking={"type": "adaptive"},
                system=[
                    {
                        "type": "text",
                        "text": SYSTEM_PROMPT,
                        # 대용량 시스템 프롬프트를 캐시에 저장 — 반복 호출 시 비용 절감
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=self.messages,
            )

        # 사용량 집계
        usage = response.usage
        self.total_cache_read += getattr(usage, "cache_read_input_tokens", 0) or 0
        self.total_cache_write += getattr(usage, "cache_creation_input_tokens", 0) or 0
        self.total_input += getattr(usage, "input_tokens", 0) or 0
        self.total_output += getattr(usage, "output_tokens", 0) or 0
        self.turn_count += 1

        # 응답에서 텍스트 추출 (thinking 블록 제외)
        answer = ""
        for block in response.content:
            if block.type == "text":
                answer = block.text
                break

        self.messages.append({"role": "assistant", "content": answer})
        return answer, format_cache_stats(usage)

    def clear(self):
        self.messages.clear()
        self.turn_count = 0

    def show_history(self):
        if not self.messages:
            console.print("[dim]대화 내역이 없습니다.[/dim]")
            return
        for i, msg in enumerate(self.messages):
            role = "👤 사용자" if msg["role"] == "user" else "🤖 세무사"
            style = "cyan" if msg["role"] == "user" else "green"
            content = msg["content"]
            if len(content) > 200:
                content = content[:200] + "..."
            console.print(f"[{style}][{i+1}] {role}:[/{style}] {content}")

    def show_cache_stats(self):
        console.print(
            Panel(
                f"[bold]누적 토큰 사용량[/bold]\n\n"
                f"  입력 토큰:      [cyan]{self.total_input:>10,}[/cyan]\n"
                f"  캐시 읽기:      [green]{self.total_cache_read:>10,}[/green]  "
                f"[dim](약 90% 할인 적용)[/dim]\n"
                f"  캐시 쓰기:      [yellow]{self.total_cache_write:>10,}[/yellow]  "
                f"[dim](25% 추가 비용)[/dim]\n"
                f"  출력 토큰:      [cyan]{self.total_output:>10,}[/cyan]\n"
                f"  총 대화 횟수:   [bold]{self.turn_count:>10,}[/bold]",
                title="캐시 사용 현황",
                border_style="blue",
            )
        )


def main():
    console.print(Text(BANNER, style="bold blue"))
    console.print(Panel(HELP_TEXT, title="[bold]도움말[/bold]", border_style="cyan", box=box.ROUNDED))

    agent = TaxAgent()
    console.print("\n[bold green]세무사 에이전트가 준비되었습니다. 세금 관련 질문을 입력하세요.[/bold green]\n")

    while True:
        try:
            user_input = Prompt.ask("[bold cyan]질문[/bold cyan]").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[bold yellow]종료합니다.[/bold yellow]")
            break

        if not user_input:
            continue

        cmd = user_input.lower()

        if cmd in ("/quit", "/exit", "/q"):
            console.print("[bold yellow]종료합니다. 감사합니다.[/bold yellow]")
            break

        elif cmd == "/clear":
            agent.clear()
            console.print("[bold green]대화가 초기화되었습니다.[/bold green]")
            continue

        elif cmd == "/history":
            agent.show_history()
            continue

        elif cmd == "/cache":
            agent.show_cache_stats()
            continue

        elif cmd == "/help":
            console.print(Panel(HELP_TEXT, title="[bold]도움말[/bold]", border_style="cyan"))
            continue

        # 일반 질문 처리
        try:
            answer, stats = agent.chat(user_input)
            console.print(
                Panel(
                    Markdown(answer),
                    title="[bold green]🏛️ 세무사 에이전트 답변[/bold green]",
                    border_style="green",
                    subtitle=f"[dim]{stats}[/dim]",
                )
            )
        except anthropic.RateLimitError:
            console.print("[bold red]오류:[/] API 요청 한도를 초과했습니다. 잠시 후 다시 시도하세요.")
        except anthropic.AuthenticationError:
            console.print("[bold red]오류:[/] API 키가 유효하지 않습니다. ANTHROPIC_API_KEY를 확인하세요.")
        except anthropic.APIConnectionError:
            console.print("[bold red]오류:[/] 네트워크 연결에 실패했습니다. 인터넷 연결을 확인하세요.")
        except anthropic.APIStatusError as e:
            console.print(f"[bold red]API 오류 ({e.status_code}):[/] {e.message}")
        except Exception as e:
            console.print(f"[bold red]예상치 못한 오류:[/] {e}")


if __name__ == "__main__":
    main()
