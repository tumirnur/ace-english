from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class SimulatorAction:
    action_type: str
    node_id: str
    clicks_delta: int
    score_delta: float
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class StudentSession:
    student_id: int
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    extra_clicks: int = 0
    extra_score_sum: float = 0.0
    extra_assessments: int = 0
    extra_forum_clicks: int = 0
    extra_resource_clicks: int = 0
    actions: list[SimulatorAction] = field(default_factory=list)
    node_progress: dict[str, dict] = field(default_factory=dict)


_sessions: dict[int, StudentSession] = {}


def get_or_create_session(student_id: int) -> StudentSession:
    if student_id not in _sessions:
        _sessions[student_id] = StudentSession(student_id=student_id)
    return _sessions[student_id]


def record_action(student_id: int, action: SimulatorAction) -> None:
    s = get_or_create_session(student_id)
    s.actions.append(action)
    s.extra_clicks += action.clicks_delta
    s.extra_score_sum += action.score_delta
    if action.score_delta > 0:
        s.extra_assessments += 1
    if action.action_type == "forum_interaction":
        s.extra_forum_clicks += action.clicks_delta
    elif action.action_type in ("material_view", "click"):
        s.extra_resource_clicks += action.clicks_delta


def update_node_progress(student_id: int, node_id: str, *, completed: bool, had_error: bool) -> None:
    s = get_or_create_session(student_id)
    prog = s.node_progress.setdefault(node_id, {"completed": False, "errors": 0})
    if completed:
        prog["completed"] = True
    if had_error:
        prog["errors"] += 1


def get_session_deltas(student_id: int) -> dict:
    s = _sessions.get(student_id)
    if not s:
        return {
            "extra_clicks": 0, "extra_score_sum": 0.0,
            "extra_assessments": 0, "extra_forum_clicks": 0,
            "extra_resource_clicks": 0, "node_progress": {},
        }
    return {
        "extra_clicks": s.extra_clicks,
        "extra_score_sum": s.extra_score_sum,
        "extra_assessments": s.extra_assessments,
        "extra_forum_clicks": s.extra_forum_clicks,
        "extra_resource_clicks": s.extra_resource_clicks,
        "node_progress": s.node_progress,
    }


def reset_session(student_id: int) -> None:
    _sessions.pop(student_id, None)
