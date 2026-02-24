#!/usr/bin/env python3
"""Generate a styled one-page project PDF without external dependencies."""

from __future__ import annotations

from pathlib import Path
import textwrap

PAGE_WIDTH = 612
PAGE_HEIGHT = 792
MARGIN = 16


def pdf_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def rgb(color: tuple[int, int, int]) -> str:
    r, g, b = color
    return f"{r / 255:.4f} {g / 255:.4f} {b / 255:.4f}"


def y_from_top(top: float, height: float = 0.0) -> float:
    return PAGE_HEIGHT - top - height


def wrap_for_width(text: str, width_pts: float, font_size: int) -> list[str]:
    chars = max(12, int(width_pts / (font_size * 0.52)))
    return textwrap.wrap(text, width=chars, break_long_words=False, break_on_hyphens=False)


class PdfCanvas:
    def __init__(self) -> None:
        self.commands: list[str] = []

    def rect(
        self,
        x: float,
        top: float,
        width: float,
        height: float,
        fill: tuple[int, int, int],
        stroke: tuple[int, int, int],
        line_width: float = 1.0,
    ) -> None:
        y = y_from_top(top, height)
        self.commands.append(f"{rgb(fill)} rg")
        self.commands.append(f"{rgb(stroke)} RG")
        self.commands.append(f"{line_width:.2f} w")
        self.commands.append(f"{x:.2f} {y:.2f} {width:.2f} {height:.2f} re B")

    def line(
        self,
        x1: float,
        top1: float,
        x2: float,
        top2: float,
        color: tuple[int, int, int],
        line_width: float = 0.8,
    ) -> None:
        y1 = y_from_top(top1)
        y2 = y_from_top(top2)
        self.commands.append(f"{rgb(color)} RG")
        self.commands.append(f"{line_width:.2f} w")
        self.commands.append(f"{x1:.2f} {y1:.2f} m {x2:.2f} {y2:.2f} l S")

    def text(
        self,
        x: float,
        top: float,
        text: str,
        font: str = "F1",
        size: int = 10,
        color: tuple[int, int, int] = (30, 41, 59),
    ) -> None:
        y = y_from_top(top, size)
        self.commands.extend(
            [
                "BT",
                f"/{font} {size} Tf",
                f"{rgb(color)} rg",
                f"1 0 0 1 {x:.2f} {y:.2f} Tm",
                f"({pdf_escape(text)}) Tj",
                "ET",
            ]
        )

    def paragraph(
        self,
        x: float,
        top: float,
        width: float,
        text: str,
        size: int = 10,
        line_gap: int = 4,
        font: str = "F1",
        color: tuple[int, int, int] = (30, 41, 59),
    ) -> float:
        cur_top = top
        for line in wrap_for_width(text, width, size):
            self.text(x, cur_top, line, font=font, size=size, color=color)
            cur_top += size + line_gap
        return cur_top

    def bullets(
        self,
        x: float,
        top: float,
        width: float,
        items: list[str],
        size: int = 10,
        line_gap: int = 3,
        color: tuple[int, int, int] = (30, 41, 59),
    ) -> float:
        cur_top = top
        for item in items:
            lines = wrap_for_width(item, width - 14, size)
            for idx, line in enumerate(lines):
                prefix = "- " if idx == 0 else "  "
                self.text(x, cur_top, f"{prefix}{line}", font="F1", size=size, color=color)
                cur_top += size + line_gap
            cur_top += 2
        return cur_top

    def numbered_list(
        self,
        x: float,
        top: float,
        width: float,
        items: list[str],
        size: int = 10,
        line_gap: int = 3,
        color: tuple[int, int, int] = (30, 41, 59),
    ) -> float:
        cur_top = top
        for idx, item in enumerate(items, start=1):
            lines = wrap_for_width(item, width - 16, size)
            for line_index, line in enumerate(lines):
                prefix = f"{idx}. " if line_index == 0 else "   "
                self.text(x, cur_top, f"{prefix}{line}", font="F1", size=size, color=color)
                cur_top += size + line_gap
            cur_top += 1
        return cur_top

    def stream(self) -> bytes:
        return ("\n".join(self.commands) + "\n").encode("latin-1")


def build_layout_stream() -> bytes:
    colors = {
        "bg": (250, 251, 253),
        "card_fill": (242, 245, 249),
        "card_border": (195, 208, 221),
        "title": (18, 31, 46),
        "subtitle": (67, 80, 95),
        "section": (8, 125, 109),
        "text": (34, 46, 61),
        "muted_border": (180, 214, 206),
        "muted_fill": (229, 245, 241),
        "chip_fill": (232, 247, 243),
        "chip_border": (133, 204, 188),
    }

    c = PdfCanvas()
    c.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, fill=colors["bg"], stroke=colors["bg"], line_width=0)

    c.text(
        MARGIN + 12,
        20,
        "Autonomous Agentic Trader - Project One-Pager",
        font="F2",
        size=24,
        color=colors["title"],
    )
    c.text(
        MARGIN + 12,
        50,
        "Multi-agent trading simulation platform with tool-gated execution and operator visibility.",
        font="F1",
        size=11,
        color=colors["subtitle"],
    )
    c.text(
        MARGIN + 12,
        66,
        "Research/education simulation; not financial advice.",
        font="F1",
        size=10,
        color=colors["subtitle"],
    )

    row_top = 82
    row_height = 300
    gap = 10
    card_width = (PAGE_WIDTH - (2 * MARGIN) - gap) / 2
    left_x = MARGIN
    right_x = left_x + card_width + gap
    pad = 10

    c.rect(left_x, row_top, card_width, row_height, colors["card_fill"], colors["card_border"], line_width=1.0)
    c.text(left_x + pad, row_top + 14, "PROBLEM", font="F2", size=12, color=colors["section"])
    problem = (
        "Most trading demos are either chat-only with no execution path or hardcoded scripts with limited"
        " transparency. Reviewers struggle to see how agent reasoning becomes controlled actions, how failures"
        " are handled, and how portfolio outcomes are explained in real time."
    )
    c.paragraph(
        left_x + pad,
        row_top + 38,
        card_width - (2 * pad),
        problem,
        size=11,
        line_gap=4,
        font="F1",
        color=colors["text"],
    )

    c.rect(right_x, row_top, card_width, row_height, colors["card_fill"], colors["card_border"], line_width=1.0)
    c.text(right_x + pad, row_top + 14, "SOLUTION FEATURES", font="F2", size=12, color=colors["section"])
    features = [
        "Four autonomous trader personas with alternating trade/rebalance cycles.",
        "MCP tool boundaries for accounts, market pricing, research, and memory.",
        "Resilient market pricing path: Polygon -> cache -> web -> unavailable.",
        "Execution safety checks block invalid quantities and unavailable prices.",
        "Control APIs for scheduler start, stop, status, and account reset.",
        "Dashboard with structured logs, trace events, holdings, and timeline views.",
        "Read-only and market-auto runtime modes for safer cloud demos.",
    ]
    c.bullets(
        right_x + pad,
        row_top + 38,
        card_width - (2 * pad),
        features,
        size=10,
        line_gap=3,
        color=colors["text"],
    )

    arch_top = 392
    arch_height = 160
    full_width = PAGE_WIDTH - (2 * MARGIN)
    c.rect(MARGIN, arch_top, full_width, arch_height, colors["card_fill"], colors["card_border"], line_width=1.0)
    c.text(MARGIN + pad, arch_top + 14, "ARCHITECTURE", font="F2", size=12, color=colors["section"])

    inner_pad = 10
    c.rect(
        MARGIN + pad,
        arch_top + 36,
        full_width - (2 * pad),
        94,
        colors["muted_fill"],
        colors["muted_border"],
        line_width=0.9,
    )
    arch_items = [
        "UI calls FastAPI for trader snapshots, logs, market status, and scheduler controls.",
        "Scheduler manages the trading engine lifecycle and run cadence.",
        "Trader Engine executes persona agents across trade and rebalance cycles.",
        "Agents call MCP tool servers for accounts, market data, and optional research memory.",
        "Tool calls persist transactions, logs, and market snapshots to State Store.",
        "Dashboard refresh exposes portfolio movement and operational telemetry.",
    ]
    c.numbered_list(
        MARGIN + pad + inner_pad,
        arch_top + 47,
        full_width - (2 * pad) - (2 * inner_pad),
        arch_items,
        size=10,
        line_gap=2,
        color=colors["text"],
    )

    chip_y = arch_top + 136
    chips = [
        "Control plane + data plane split",
        "MCP tool boundary",
        "Resilient price fallback",
    ]
    chip_x = MARGIN + pad
    for chip in chips:
        chip_w = 18 + (len(chip) * 4.9)
        c.rect(chip_x, chip_y, chip_w, 16, colors["chip_fill"], colors["chip_border"], line_width=0.8)
        c.text(chip_x + 7, chip_y + 4, chip, font="F1", size=9, color=colors["section"])
        chip_x += chip_w + 8

    stack_top = 560
    stack_height = 216
    c.rect(MARGIN, stack_top, full_width, stack_height, colors["card_fill"], colors["card_border"], line_width=1.0)
    c.text(MARGIN + pad, stack_top + 14, "TECHNOLOGY STACK", font="F2", size=12, color=colors["section"])

    rows = [
        ("Frontend", "Next.js static export, TypeScript dashboard, portfolio and log visualizations"),
        ("Backend", "FastAPI, Uvicorn, Pydantic services, scheduler control API"),
        ("AI/Agents", "OpenAI Agents SDK, multi-model routing, MCP tool servers over stdio"),
        ("Data/State", "State Store (SQLite + memory), account ledgers, logs, market cache"),
        ("Integrations", "Polygon market data, Brave Search, fetch/memory MCP services"),
        ("Deployment", "Docker, AWS ECR + EC2, Terraform, GitHub Actions, SSM deployment"),
    ]

    label_w = 102
    row_top = stack_top + 36
    row_left = MARGIN + pad
    row_right = MARGIN + full_width - pad
    line_color = (205, 214, 224)
    text_w = full_width - (2 * pad) - label_w - 6

    for label, value in rows:
        c.text(row_left, row_top, label, font="F2", size=10, color=colors["text"])
        value_lines = wrap_for_width(value, text_w, 10)
        line_top = row_top
        for line in value_lines:
            c.text(row_left + label_w + 6, line_top, line, font="F1", size=10, color=colors["text"])
            line_top += 12
        row_bottom = line_top + 2
        c.line(row_left, row_bottom, row_right, row_bottom, color=line_color, line_width=0.6)
        row_top = row_bottom + 4

    return c.stream()


def build_pdf(content_stream: bytes) -> bytes:
    objects: list[bytes] = []
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>")
    objects.append(
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 5 0 R /F2 6 0 R >> >> /Contents 4 0 R >>"
    )
    objects.append(
        b"<< /Length " + str(len(content_stream)).encode("ascii") + b" >>\nstream\n"
        + content_stream
        + b"endstream"
    )
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>")

    pdf = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{i} 0 obj\n".encode("ascii"))
        pdf.extend(obj)
        pdf.extend(b"\nendobj\n")

    xref_start = len(pdf)
    count = len(objects) + 1
    pdf.extend(f"xref\n0 {count}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        pdf.extend(f"{off:010d} 00000 n \n".encode("ascii"))

    pdf.extend(f"trailer\n<< /Size {count} /Root 1 0 R >>\n".encode("ascii"))
    pdf.extend(f"startxref\n{xref_start}\n%%EOF\n".encode("ascii"))
    return bytes(pdf)


def main() -> None:
    out_pdf = Path("deliverables/project-one-pager.pdf")
    content = build_layout_stream()
    pdf_bytes = build_pdf(content)
    out_pdf.write_bytes(pdf_bytes)
    print(f"Wrote {out_pdf}")


if __name__ == "__main__":
    main()
