"""GitHub-style diff panels for the terminal."""

import re

from rich import box
from rich.panel import Panel
from rich.style import Style
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Span, Text

HUNK = re.compile(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@")
DIFF_PATTERN = re.compile(
    r"(?:^--- .*\n^\+\+\+ .*\n(?:^@@.*\n(?:^[+\- ].*\n|^\\ No newline.*\n)*)+)+",
    re.MULTILINE,
)

COLLAPSED_LINES = 20
BORDER = "#3a3a3a"
PANEL_BG = "#1a1a1a"
ADD_BG = "on #0d2818"
DEL_BG = "on #3d1418"
SIGN_ADD = "bold #4ade80"
SIGN_DEL = "bold #f87171"
NUM_STYLE = "#5b6270"
GAP = "⋯"


def _highlight(path: str, code: str) -> list[Text]:
    if not code:
        return []
    try:
        from pygments.lexers import guess_lexer_for_filename
        lexer = guess_lexer_for_filename(path, code)
        lexer_name = lexer.aliases[0] if lexer.aliases else "text"
    except Exception:
        lexer_name = "text"
    try:
        syntax = Syntax(code, lexer_name, theme="monokai", background_color="default")
        highlighted = syntax.highlight(code)
        highlighted.spans = [
            Span(s.start, s.end, Style(
                color=s.style.color, bold=s.style.bold,
                italic=s.style.italic, underline=s.style.underline,
            ))
            for s in highlighted.spans if isinstance(s.style, Style)
        ]
        highlighted.style = ""
        highlighted.expand_tabs(4)
        return highlighted.split("\n")
    except Exception:
        return [Text(line) for line in code.split("\n")]


def _parse_rows(output: str) -> tuple[str, list[tuple[int | None, str, str]]]:
    """Parse a unified diff (with optional prose prefix) into (path, rows)."""
    path = ""
    for line in output.splitlines():
        if line.startswith("Wrote ") or line.startswith("Edited "):
            path = line.split(maxsplit=1)[1].rstrip(".")
    rows: list[tuple[int | None, str, str]] = []
    new_line = 0
    in_diff = False
    first_hunk = True
    for line in output.splitlines():
        if line.startswith("--- "):
            in_diff = True
        elif not in_diff:
            if not any(l.startswith(("Wrote ", "Edited ")) for l in output.splitlines()[:output.splitlines().index(line)]):
                continue
        if not in_diff:
            continue
        if line.startswith("+++ "):
            path = line[4:].split("\t")[0].strip() or path
            continue
        if HUNK.match(line):
            new_line = int(HUNK.match(line).group(2))
            if not first_hunk:
                rows.append((None, GAP, ""))
            first_hunk = False
            continue
        if line.startswith("+"):
            rows.append((new_line, "+", line[1:]))
            new_line += 1
        elif line.startswith("-"):
            rows.append((None, "-", line[1:]))
        elif line.startswith("\\"):
            continue
        elif line.startswith(" "):
            rows.append((new_line, " ", line[1:]))
            new_line += 1
    return path, rows


def render_diff(output: str, limit: int | None = COLLAPSED_LINES, number: int = 0) -> tuple[Panel, int]:
    """Render a tool output containing a unified diff as a syntax-highlighted panel."""
    path, rows = _parse_rows(output)
    if not rows:
        label = path or "file"
        return Panel(Text(f"(no changes to {label})", style="dim"),
                     box=box.ROUNDED, border_style=BORDER, padding=(0, 1)), 0

    added = sum(1 for _, s, _ in rows if s == "+")
    removed = sum(1 for _, s, _ in rows if s == "-")

    content_lines = [c for _, s, c in rows if s != GAP]
    hl_lines = _highlight(path, "\n".join(content_lines))
    hl_idx = 0

    gutter = max((len(str(r[0] or "")) for r in rows), default=1)
    gutter = max(gutter, 1)

    shown = rows if limit is None else rows[:limit]
    hidden = len(rows) - len(shown)

    table = Table.grid(expand=True, padding=0)
    table.add_column(width=gutter + 1, justify="right", no_wrap=True)
    table.add_column(width=2, justify="center", no_wrap=True)
    table.add_column(ratio=1)

    for line_num, sign, content in shown:
        if sign == GAP:
            table.add_row("", Text(GAP, style="dim"), "")
            continue
        if hl_lines and hl_idx < len(hl_lines):
            code = hl_lines[hl_idx].copy()
            hl_idx += 1
        else:
            code = Text(content.expandtabs(4))
        code.overflow = "fold"
        if sign == "+":
            row_bg, sign_text = ADD_BG, Text("+", style=SIGN_ADD)
        elif sign == "-":
            row_bg, sign_text = DEL_BG, Text("-", style=SIGN_DEL)
        else:
            row_bg, sign_text = "", Text(" ")
        table.add_row(
            Text(str(line_num or ""), style=NUM_STYLE),
            sign_text, code, style=row_bg,
        )

    title = Text.assemble(
        (path + "  ", "bold"),
        (f"+{added}", "green"),
        *([(f" -{removed}", "red")] if removed else []),
    )
    subtitle = Text(f"... {hidden} more lines  /expand {number}", style="dim") if hidden and number else None

    panel = Panel(
        table, title=title, title_align="left",
        subtitle=subtitle, subtitle_align="left",
        box=box.ROUNDED, border_style=BORDER,
        style=f"on {PANEL_BG}", padding=(0, 0),
    )
    return panel, hidden


def split_diff_and_text(text: str) -> list[tuple[bool, str]]:
    """Split text into (is_diff, segment) pairs, isolating unified diff blocks."""
    if not text:
        return [(False, "")]
    segments = []
    last = 0
    for match in DIFF_PATTERN.finditer(text):
        if match.start() > last:
            segments.append((False, text[last:match.start()]))
        segments.append((True, match.group()))
        last = match.end()
    if last < len(text):
        segments.append((False, text[last:]))
    return segments
