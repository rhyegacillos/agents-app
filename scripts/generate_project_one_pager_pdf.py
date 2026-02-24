#!/usr/bin/env python3
"""Generate a one-page PDF from deliverables/project-one-pager.md without external deps."""

from __future__ import annotations

from pathlib import Path
import textwrap

PAGE_WIDTH = 612
PAGE_HEIGHT = 792
LEFT_MARGIN = 54
TOP_Y = 754
LINE_WIDTH_CHARS = 94


def pdf_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def wrap_text(text: str, width: int = LINE_WIDTH_CHARS) -> list[str]:
    return textwrap.wrap(text, width=width, break_long_words=False, break_on_hyphens=False)


def build_layout() -> list[tuple[str, int, int, str]]:
    # tuple: (font_id, size, x, text)
    rows: list[tuple[str, int, int, str]] = []

    rows.append(("F2", 20, LEFT_MARGIN, "Autonomous Agentic Trader - Project One-Pager"))
    rows.append(("F1", 10, LEFT_MARGIN, "Multi-agent AI trading simulation platform for portfolio and LinkedIn showcase"))
    rows.append(("F1", 10, LEFT_MARGIN, "Research/education simulation; not financial advice."))
    rows.append(("", 0, LEFT_MARGIN, ""))

    rows.append(("F2", 12, LEFT_MARGIN, "Problem"))
    problem = (
        "Most trading demos are either chat-only with no execution path, or hardcoded scripts with no transparent"
        " reasoning. This project combines autonomous LLM decision-making, tool-gated execution, and live"
        " observability in one deployable system."
    )
    for line in wrap_text(problem):
        rows.append(("F1", 10, LEFT_MARGIN, line))
    rows.append(("", 0, LEFT_MARGIN, ""))

    rows.append(("F2", 12, LEFT_MARGIN, "Key Features"))
    feature_items = [
        "Four trader personas (Warren, George, Ray, Cathie) running scheduled trade/rebalance cycles.",
        "MCP tool boundaries for account actions, market prices, web research, and memory.",
        "Resilient pricing chain: Polygon -> cache -> web -> unavailable; invalid prices are blocked.",
        "FastAPI lifecycle controls: start, stop, status, and reset for runtime operations.",
        "Next.js dashboard with structured logs, trace events, holdings, transactions, and timeline.",
        "Read-only and market-auto runtime modes for safer cloud demo operations.",
    ]
    for item in feature_items:
        wrapped = wrap_text(f"- {item}")
        for idx, line in enumerate(wrapped):
            x = LEFT_MARGIN if idx == 0 else LEFT_MARGIN + 14
            rows.append(("F1", 10, x, line))
    rows.append(("", 0, LEFT_MARGIN, ""))

    rows.append(("F2", 12, LEFT_MARGIN, "Architecture"))
    architecture_items = [
        "Single Docker container serves FastAPI APIs and static Next.js UI on port 8000.",
        "FastAPI is the control plane; trading engine runs as a managed child process data plane.",
        "Trader agents call MCP servers instead of mutating storage directly.",
        "State persists in SQLite tables (accounts, logs, market) plus optional per-trader memory DBs.",
        "External integrations: LLM providers, Polygon market data, and research MCP tools.",
    ]
    for item in architecture_items:
        wrapped = wrap_text(f"- {item}")
        for idx, line in enumerate(wrapped):
            x = LEFT_MARGIN if idx == 0 else LEFT_MARGIN + 14
            rows.append(("F1", 10, x, line))
    rows.append(("", 0, LEFT_MARGIN, ""))

    rows.append(("F2", 12, LEFT_MARGIN, "Stack"))
    stack_items = [
        "Backend: FastAPI, Uvicorn, Python 3.12",
        "Agent Runtime: OpenAI Agents SDK + MCP tool servers (stdio)",
        "Frontend: Next.js static export with TypeScript",
        "Data: SQLite",
        "Infra: Docker, AWS EC2 + ECR, Terraform, GitHub Actions (OIDC), SSM redeploy",
    ]
    for item in stack_items:
        rows.append(("F1", 10, LEFT_MARGIN, f"- {item}"))

    rows.append(("", 0, LEFT_MARGIN, ""))
    rows.append(("F2", 12, LEFT_MARGIN, "Outcome"))
    outcome = (
        "A production-style, end-to-end agentic application demonstrating decision intelligence, controlled tool"
        " execution, observability, and cloud-ready deployment workflow."
    )
    for line in wrap_text(outcome):
        rows.append(("F1", 10, LEFT_MARGIN, line))

    return rows


def make_content_stream(rows: list[tuple[str, int, int, str]]) -> bytes:
    commands = []
    y = TOP_Y
    for font_id, size, x, text in rows:
        if not font_id:
            y -= 8
            continue
        commands.append("BT")
        commands.append(f"/{font_id} {size} Tf")
        commands.append(f"1 0 0 1 {x} {y} Tm")
        commands.append(f"({pdf_escape(text)}) Tj")
        commands.append("ET")
        if size >= 20:
            y -= 22
        elif size >= 12:
            y -= 16
        else:
            y -= 13

    if y < 42:
        raise RuntimeError("Content overflowed the single page. Reduce text before generating PDF.")

    return ("\n".join(commands) + "\n").encode("latin-1")


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
    rows = build_layout()
    content = make_content_stream(rows)
    pdf_bytes = build_pdf(content)
    out_pdf.write_bytes(pdf_bytes)
    print(f"Wrote {out_pdf}")


if __name__ == "__main__":
    main()
