from __future__ import annotations

from typing import Optional

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.core.graph import (
    KNOWLEDGE_GRAPH,
    check_answer,
    get_graph_for_frontend,
    get_next_question,
)
from app.core.session_store import (
    SimulatorAction,
    get_session_deltas,
    get_or_create_session,
    record_action,
    reset_session,
    update_node_progress,
)
from app.db.database import get_session as get_db
from app.db.oulad_models import AssessmentScore, OuladStudent, WeeklyActivity
from app.ml.oulad_ml import OuladMLEngine

router = APIRouter(prefix="/api", tags=["OULAD Adaptive Platform"])

_BENCHMARK = {
    "avg_weekly_clicks": 18,
    "avg_assessment_score": 65.0,
    "active_weeks_ratio": 0.75,
    "forum_clicks_per_week": 3.0,
}



class SimulateActionRequest(BaseModel):
    action_type: str = Field(...)
    node_id: str
    question_index: Optional[int] = None
    selected_option: Optional[int] = None



def _aggregate(student_id: int, db: Session, up_to_week: Optional[int] = None) -> dict:
    acts = db.exec(
        select(WeeklyActivity).where(WeeklyActivity.student_id == student_id)
    ).all()
    asmts = db.exec(
        select(AssessmentScore).where(AssessmentScore.student_id == student_id)
    ).all()

    if up_to_week is not None:
        acts = [a for a in acts if a.week <= up_to_week]
        asmts = [a for a in asmts if a.week_submitted <= up_to_week]

    total_clicks = sum(a.total_clicks for a in acts)
    forum_clicks = sum(a.forum_clicks for a in acts)
    resource_clicks = sum(a.resource_clicks for a in acts)
    active_weeks = len([a for a in acts if a.total_clicks > 0])

    scores = [a.score for a in asmts if a.is_submitted]
    avg_score = float(np.mean(scores)) if scores else 0.0

    weeks_with_data = sorted({a.week for a in acts})
    max_week = max(weeks_with_data) if weeks_with_data else (up_to_week or 1)

    return {
        "total_clicks": total_clicks,
        "avg_weekly_clicks": total_clicks / max(max_week, 1),
        "avg_score": avg_score,
        "assessments_submitted": len(scores),
        "active_weeks": active_weeks,
        "forum_clicks": forum_clicks,
        "resource_clicks": resource_clicks,
        "max_week": max_week,
    }


def _predict(agg: dict, week: int) -> dict:
    return OuladMLEngine.get().predict(
        total_clicks=agg["total_clicks"],
        avg_weekly_clicks=agg["avg_weekly_clicks"],
        assessment_avg_score=agg["avg_score"],
        assessments_submitted=agg["assessments_submitted"],
        active_weeks=agg["active_weeks"],
        forum_clicks=agg["forum_clicks"],
        resource_clicks=agg["resource_clicks"],
        week_number=week,
    )


def _recommendations(agg: dict, week: int) -> list[str]:
    recs = []
    expected = _BENCHMARK["avg_weekly_clicks"] * week
    if agg["total_clicks"] < expected * 0.6:
        recs.append(
            f"📚 Низкая активность: {agg['total_clicks']} кликов "
            f"при ожидаемых ~{int(expected)}. Уделяйте больше времени материалам."
        )
    if agg["avg_score"] < _BENCHMARK["avg_assessment_score"]:
        recs.append(
            f"📝 Средний балл {agg['avg_score']:.1f} ниже нормы "
            f"({_BENCHMARK['avg_assessment_score']:.0f}). Повторите пройденные темы."
        )
    if agg["active_weeks"] < week * _BENCHMARK["active_weeks_ratio"] * 0.7:
        recs.append(
            "⏰ Много пропущенных недель. "
            "Регулярные занятия важнее интенсивных сессий раз в месяц."
        )
    forum_pw = agg["forum_clicks"] / max(week, 1)
    if forum_pw < _BENCHMARK["forum_clicks_per_week"] * 0.5:
        recs.append(
            "💬 Мало активности на форуме. "
            "Обсуждение с однокурсниками улучшает понимание материала."
        )
    return recs or ["✅ Отличный темп! Продолжайте в том же духе."]



@router.get("/students/list")
def list_students(db: Session = Depends(get_db)):
    students = db.exec(
        select(OuladStudent.id, OuladStudent.final_result,
               OuladStudent.code_module, OuladStudent.code_presentation)
    ).all()
    return [
        {"id": s[0], "final_result": s[1], "group": f"{s[2]}-{s[3]}"}
        for s in students
    ]


@router.get("/student/{student_id}/dashboard")
def get_dashboard(student_id: int, db: Session = Depends(get_db)):
    student = db.get(OuladStudent, student_id)
    if not student:
        raise HTTPException(404, f"Студент {student_id} не найден")

    all_weeks = sorted({
        a.week
        for a in db.exec(
            select(WeeklyActivity).where(WeeklyActivity.student_id == student_id)
        ).all()
    })
    if not all_weeks:
        raise HTTPException(404, "Нет данных об активности студента")

    sampled = all_weeks[::2] if len(all_weeks) > 20 else all_weeks
    weeks_data = []
    for w in sampled:
        agg = _aggregate(student_id, db, up_to_week=w)
        pred = _predict(agg, w)
        weeks_data.append({
            "week": w,
            "total_clicks": agg["total_clicks"],
            "avg_score": round(agg["avg_score"], 1),
            "active_weeks": agg["active_weeks"],
            "prediction": pred,
        })

    current_agg = _aggregate(student_id, db)
    cur_week = max(all_weeks)
    cur_pred = _predict(current_agg, cur_week)

    expected_clicks = _BENCHMARK["avg_weekly_clicks"] * cur_week
    benchmark_comparison = {
        "clicks": {
            "student": current_agg["total_clicks"],
            "benchmark": int(expected_clicks),
            "ratio": round(current_agg["total_clicks"] / max(expected_clicks, 1), 2),
        },
        "score": {
            "student": round(current_agg["avg_score"], 1),
            "benchmark": _BENCHMARK["avg_assessment_score"],
            "ratio": round(current_agg["avg_score"] / _BENCHMARK["avg_assessment_score"], 2),
        },
        "activity": {
            "student": current_agg["active_weeks"],
            "benchmark": round(cur_week * _BENCHMARK["active_weeks_ratio"], 1),
            "ratio": round(
                current_agg["active_weeks"] / max(cur_week * _BENCHMARK["active_weeks_ratio"], 1), 2
            ),
        },
    }

    return {
        "student_id": student_id,
        "final_result": student.final_result,
        "total_weeks": cur_week,
        "weeks_data": weeks_data,
        "current_week": cur_week,
        "current_prediction": cur_pred,
        "benchmark_comparison": benchmark_comparison,
        "recommendations": _recommendations(current_agg, cur_week),
    }


@router.get("/student/{student_id}/graph")
def get_graph(student_id: int, db: Session = Depends(get_db)):
    if not db.get(OuladStudent, student_id):
        raise HTTPException(404, "Студент не найден")
    deltas = get_session_deltas(student_id)
    return {
        "graph": get_graph_for_frontend(),
        "session_progress": deltas["node_progress"],
        "session_extra_clicks": deltas["extra_clicks"],
        "session_extra_score": deltas["extra_score_sum"],
    }


@router.post("/student/{student_id}/simulate-action")
def simulate_action(
    student_id: int,
    req: SimulateActionRequest,
    db: Session = Depends(get_db),
):
    if not db.get(OuladStudent, student_id):
        raise HTTPException(404, "Студент не найден")

    _deltas = {
        "click":             (3, 0.0),
        "material_view":     (5, 0.0),
        "forum_interaction": (4, 0.0),
        "answer_correct":    (2, 15.0),
        "answer_wrong":      (2, 0.0),
    }
    clicks_d, score_d = _deltas.get(req.action_type, (1, 0.0))

    record_action(student_id, SimulatorAction(
        action_type=req.action_type,
        node_id=req.node_id,
        clicks_delta=clicks_d,
        score_delta=score_d,
    ))

    base = _aggregate(student_id, db)
    d = get_session_deltas(student_id)

    total_new = base["total_clicks"] + d["extra_clicks"]
    n_asmts_new = base["assessments_submitted"] + d["extra_assessments"]
    score_new = (
        (base["avg_score"] * base["assessments_submitted"] + d["extra_score_sum"])
        / max(n_asmts_new, 1)
    )
    enhanced = {
        "total_clicks": total_new,
        "avg_weekly_clicks": total_new / max(base["max_week"], 1),
        "avg_score": score_new,
        "assessments_submitted": n_asmts_new,
        "active_weeks": base["active_weeks"],
        "forum_clicks": base["forum_clicks"] + d["extra_forum_clicks"],
        "resource_clicks": base["resource_clicks"] + d["extra_resource_clicks"],
    }
    new_pred = _predict(enhanced, base["max_week"])

    answer_result = None
    remediation_node = None
    if req.question_index is not None and req.selected_option is not None:
        answer_result = check_answer(req.node_id, req.question_index, req.selected_option)
        had_error = not answer_result["is_correct"]
        update_node_progress(student_id, req.node_id,
                             completed=answer_result["is_correct"], had_error=had_error)
        if had_error:
            remediation_node = answer_result.get("remediation_node")

    return {
        "success": True,
        "action_recorded": req.action_type,
        "new_prediction": new_pred,
        "delta": {
            "clicks_added": float(clicks_d),
            "score_added": float(score_d),
            "total_session_clicks": float(d["extra_clicks"]),
            "total_session_score": float(d["extra_score_sum"]),
        },
        "remediation_node": remediation_node,
        "answer_result": answer_result,
    }


@router.get("/student/{student_id}/question")
def get_question(
    student_id: int,
    node_id: str = Query(...),
    question_index: int = Query(0),
    db: Session = Depends(get_db),
):
    if not db.get(OuladStudent, student_id):
        raise HTTPException(404, "Студент не найден")
    q = get_next_question(node_id, question_index)
    if not q:
        raise HTTPException(404, "Вопрос не найден")
    return q


@router.delete("/student/{student_id}/session")
def reset_student_session(student_id: int):
    reset_session(student_id)
    return {"message": "Сессия сброшена"}


@router.get("/teacher/group-stats")
def get_group_stats(
    group_id: str = Query("BBB-2014J"),
    db: Session = Depends(get_db),
):
    parts = group_id.split("-", 1)
    module = parts[0] if parts else "BBB"
    presentation = parts[1] if len(parts) > 1 else "2014J"

    students = db.exec(
        select(OuladStudent)
        .where(OuladStudent.code_module == module,
               OuladStudent.code_presentation == presentation)
        .limit(100)
    ).all()

    if not students:
        raise HTTPException(404, f"Группа {group_id} не найдена")

    engine = OuladMLEngine.get()
    cluster_dist: dict[str, int] = {}
    at_risk = []
    pass_probs = []

    for s in students:
        agg = _aggregate(s.id, db)
        if agg["max_week"] == 0:
            continue
        pred = engine.predict(
            total_clicks=agg["total_clicks"],
            avg_weekly_clicks=agg["avg_weekly_clicks"],
            assessment_avg_score=agg["avg_score"],
            assessments_submitted=agg["assessments_submitted"],
            active_weeks=agg["active_weeks"],
            forum_clicks=agg["forum_clicks"],
            resource_clicks=agg["resource_clicks"],
            week_number=agg["max_week"],
        )
        label = pred["cluster_label"]
        cluster_dist[label] = cluster_dist.get(label, 0) + 1
        fail_p = pred["probabilities"].get("Fail", 0.0)
        pass_probs.append(pred["pass_probability"])

        if fail_p > 0.30:
            at_risk.append({
                "student_id": s.id,
                "fail_probability": round(fail_p, 3),
                "pass_probability": round(pred["pass_probability"], 3),
                "cluster_label": label,
                "total_clicks": agg["total_clicks"],
                "avg_score": round(agg["avg_score"], 1),
                "week": agg["max_week"],
            })

    at_risk.sort(key=lambda x: x["fail_probability"], reverse=True)

    node_errors: dict[str, dict] = {}
    for s in students:
        for node_id, prog in get_session_deltas(s.id)["node_progress"].items():
            stats = node_errors.setdefault(node_id, {"errors": 0, "remediations": 0})
            stats["errors"] += prog.get("errors", 0)
            if prog.get("errors", 0) > 0:
                stats["remediations"] += 1

    heatmap = []
    for nid, node in KNOWLEDGE_GRAPH.items():
        st = node_errors.get(nid, {"errors": 0, "remediations": 0})
        heatmap.append({
            "node_id": nid,
            "node_title": node.title,
            "error_count": st["errors"],
            "remediation_count": st["remediations"],
            "risk_score": round(st["errors"] * 0.6 + st["remediations"] * 0.4, 2),
        })
    heatmap.sort(key=lambda x: x["risk_score"], reverse=True)

    return {
        "group_id": group_id,
        "total_students": len(students),
        "cluster_distribution": cluster_dist,
        "at_risk_students": at_risk[:20],
        "node_heatmap": heatmap,
        "avg_pass_probability": round(float(np.mean(pass_probs)) if pass_probs else 0.0, 3),
    }


@router.get("/graph/structure")
def graph_structure():
    return get_graph_for_frontend()
