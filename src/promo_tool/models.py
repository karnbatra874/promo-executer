from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field


class Line(BaseModel):
    episode: int
    number: int
    text: str
    words: int
    ts: Optional[float] = None   # explicit timestamp from the script, in seconds
    start: float = 0.0           # estimated/explicit start, seconds
    end: float = 0.0
    element_type: str = ""       # 'camera', 'action', 'dialogue', 'sound_fx', or '' for legacy
    speaker: Optional[str] = None  # speaker name for dialogue lines
    tone: Optional[str] = None     # delivery tone
    scene: Optional[int] = None    # scene number within episode

    @property
    def key(self) -> tuple[int, int]:
        return (self.episode, self.number)


class Chunk(BaseModel):
    index: int
    lines: list[Line]

    def render(self) -> str:
        return "\n".join(f"[E{l.episode}:L{l.number} {l.start:.1f}-{l.end:.1f}s] {l.text}" for l in self.lines)

class Anchor(BaseModel):
    anchor_id: str = ""
    type: str = "hook"
    episode: int
    line: int
    description: str = ""


class Segment(BaseModel):
    episode: int
    start_line: int
    end_line: int
    start_timestamp: str
    end_timestamp: str
    word_count: int


class Scores(BaseModel):
    hook_velocity: float
    context_independence: float
    cliffhanger_friction: float


class QCFlag(BaseModel):
    code: str                   # e.g. pronoun_soup
    severity: str = "warn"      # "warn" or "error"
    message: str
    suggestion: str = ""


class Promo(BaseModel):
    promo_id: str = ""
    episodes_spanned: list[int] = Field(default_factory=list)
    segments: list[Segment] = Field(default_factory=list)
    hook: str = ""
    cliffhanger: str = ""
    rationale: str = ""
    word_count: int = 0
    est_duration_sec: float = 0.0
    scores: Optional[Scores] = None
    total_score: Optional[float] = None
    tier: str = "Unscored"
    qc_flags: list[QCFlag] = Field(default_factory=list)
    needs_human_review: bool = False
    covered_lines: list[tuple[int, int]] = Field(default_factory=list)
    text: str = ""
