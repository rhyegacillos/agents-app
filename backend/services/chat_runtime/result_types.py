from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class HighRiskChatResult:
    output: str
    tool_events: List[Dict[str, Any]] = field(default_factory=list)
    llm_tokens: int = 0
