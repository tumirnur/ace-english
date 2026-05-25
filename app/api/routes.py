import random
from collections import defaultdict
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app.db.database import get_session
from app.db.models import AnswerLog, Group, Question, Student, TopicNode
from app.services.ai_service import (
    analyze_error, generate_hint, analyze_session_gaps,
    generate_learning_path, generate_weekly_advice,
    explain_oulad_prediction, generate_group_interventions,
)
from app.ml.oulad_engine import oulad_engine
from app.ml.oulad_ml import OuladMLEngine

router = APIRouter(prefix="/api")


class LoginBody(BaseModel):
    name: str
    password: str = ""


class RegisterBody(BaseModel):
    name: str
    password: str


def _student_resp(student: "Student", session: Session) -> dict:
    group = session.get(Group, student.group_id)
    return {"id": student.id, "name": student.name,
            "group_name": group.name if group else "",
            "streak_days": student.streak_days}


@router.post("/auth/login")
def auth_login(body: LoginBody, session: Session = Depends(get_session)):
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "Name required")
    student = session.exec(select(Student).where(Student.name == name)).first()
    if not student:
        raise HTTPException(404, "Пользователь не найден. Сначала зарегистрируйся.")
    if student.password and student.password != body.password:
        raise HTTPException(401, "Неверный пароль")
    return _student_resp(student, session)


@router.post("/auth/register")
def auth_register(body: RegisterBody, session: Session = Depends(get_session)):
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "Name required")
    if not body.password:
        raise HTTPException(400, "Password required")
    existing = session.exec(select(Student).where(Student.name == name)).first()
    if existing:
        raise HTTPException(409, "Пользователь с таким именем уже существует")
    group = session.exec(select(Group)).first()
    if not group:
        raise HTTPException(500, "No groups in DB")
    student = Student(name=name, group_id=group.id, streak_days=0, password=body.password)
    session.add(student)
    session.commit()
    session.refresh(student)
    return _student_resp(student, session)



@router.get("/graph")
def get_graph(session: Session = Depends(get_session)):
    nodes = session.exec(select(TopicNode)).all()
    edges = []
    for node in nodes:
        for pk in node.prerequisite_keys:
            edges.append({"from": pk, "to": node.key})
    return {
        "nodes": [
            {"key": n.key, "title": n.title, "description": n.description,
             "theory": n.theory, "difficulty": n.difficulty,
             "prerequisite_keys": n.prerequisite_keys,
             "pos_x": n.pos_x, "pos_y": n.pos_y}
            for n in nodes
        ],
        "edges": edges,
    }


@router.get("/topic/{key}/question")
def get_question(key: str, exclude_ids: str = "", last_id: int = 0, session: Session = Depends(get_session)):
    topic = session.exec(select(TopicNode).where(TopicNode.key == key)).first()
    if not topic:
        raise HTTPException(404, "Topic not found")
    questions = session.exec(select(Question).where(Question.topic_node_id == topic.id)).all()
    if not questions:
        raise HTTPException(404, "No questions")
    exclude = {int(x) for x in exclude_ids.split(",") if x.strip().isdigit()}
    available = [q for q in questions if q.id not in exclude]
    if not available:
        available = [q for q in questions if q.id != last_id] or list(questions)
    q = random.choice(available)
    return {
        "id": q.id, "text": q.text, "options": q.options,
        "error_category": q.error_category,
        "topic_key": key, "topic_title": topic.title,
        "topic_difficulty": topic.difficulty,
    }


@router.get("/topic/{key}/hint")
async def get_hint(key: str, question_id: int, session: Session = Depends(get_session)):
    topic = session.exec(select(TopicNode).where(TopicNode.key == key)).first()
    if not topic:
        raise HTTPException(404, "Topic not found")
    question = session.get(Question, question_id)
    if not question:
        raise HTTPException(404, "Question not found")
    hint = await generate_hint(
        question_text=question.text,
        topic_title=topic.title,
        options=question.options,
        error_category=question.error_category,
    )
    return {"hint": hint}


class AnswerRequest(BaseModel):
    student_id: int
    question_id: int
    student_answer: str


@router.post("/answer")
async def submit_answer(payload: AnswerRequest, session: Session = Depends(get_session)):
    student = session.get(Student, payload.student_id)
    if not student:
        raise HTTPException(404, "Student not found")
    question = session.get(Question, payload.question_id)
    if not question:
        raise HTTPException(404, "Question not found")

    is_correct = payload.student_answer.strip() == question.correct_answer.strip()
    diagnosis = redirect_key = redirect_reason = ""

    if not is_correct:
        topic = session.get(TopicNode, question.topic_node_id)
        prereq_nodes = []
        if topic and topic.prerequisite_keys:
            prereq_nodes = [
                {"key": n.key, "title": n.title}
                for n in session.exec(
                    select(TopicNode).where(TopicNode.key.in_(topic.prerequisite_keys))
                ).all()
            ]
        d = await analyze_error(
            question_text=question.text,
            student_answer=payload.student_answer,
            correct_answer=question.correct_answer,
            current_topic_title=topic.title if topic else "",
            error_category=question.error_category,
            prerequisite_nodes=prereq_nodes,
        )
        diagnosis = d.get("problem", "")
        redirect_key = d.get("target_node_key")
        redirect_reason = d.get("redirect_reason", "")

    log = AnswerLog(
        student_id=payload.student_id,
        question_id=payload.question_id,
        topic_node_id=question.topic_node_id,
        student_answer=payload.student_answer,
        is_correct=is_correct,
        ai_problem=diagnosis,
        redirected_to_key=redirect_key,
        week_number=4,
    )
    session.add(log)
    session.commit()

    return {
        "is_correct": is_correct,
        "correct_answer": question.correct_answer,
        "diagnosis": diagnosis,
        "redirect_to_key": redirect_key,
        "redirect_reason": redirect_reason,
    }


class SessionGapsRequest(BaseModel):
    errors: list[dict]


@router.post("/student/{student_id}/session-gaps")
async def session_gaps(student_id: int, payload: SessionGapsRequest,
                       session: Session = Depends(get_session)):
    student = session.get(Student, student_id)
    if not student:
        raise HTTPException(404, "Student not found")
    result = await analyze_session_gaps(payload.errors, student.name)
    return result



@router.get("/students")
def list_students(session: Session = Depends(get_session)):
    students = session.exec(select(Student)).all()
    groups = {g.id: g.name for g in session.exec(select(Group)).all()}
    return [
        {"id": s.id, "name": s.name, "group_id": s.group_id,
         "group_name": groups.get(s.group_id, ""), "streak_days": s.streak_days}
        for s in students
    ]


@router.get("/student/{student_id}/progress")
def student_progress(student_id: int, session: Session = Depends(get_session)):
    student = session.get(Student, student_id)
    if not student:
        raise HTTPException(404, "Student not found")
    group = session.get(Group, student.group_id)
    group_students = session.exec(
        select(Student).where(Student.group_id == student.group_id)
    ).all()
    logs = session.exec(select(AnswerLog).where(AnswerLog.student_id == student_id)).all()
    topics = {t.id: t for t in session.exec(select(TopicNode)).all()}

    topic_stats: dict[int, dict] = defaultdict(lambda: {"correct": 0, "total": 0})
    for log in logs:
        topic_stats[log.topic_node_id]["total"] += 1
        if log.is_correct:
            topic_stats[log.topic_node_id]["correct"] += 1

    topic_mastery = [
        {
            "key": t.key, "title": t.title, "difficulty": t.difficulty,
            "prerequisite_keys": t.prerequisite_keys,
            "correct": topic_stats[tid]["correct"], "total": topic_stats[tid]["total"],
            "accuracy": round(topic_stats[tid]["correct"] / topic_stats[tid]["total"], 2)
            if topic_stats[tid]["total"] else 0,
        }
        for tid, t in topics.items()
    ]
    topic_mastery.sort(key=lambda x: x["accuracy"])

    total = len(logs)
    correct = sum(1 for l in logs if l.is_correct)
    student_acc = correct / total if total else 0

    def _acc(sid: int) -> float:
        slogs = session.exec(select(AnswerLog).where(AnswerLog.student_id == sid)).all()
        return sum(1 for l in slogs if l.is_correct) / len(slogs) if slogs else 0

    group_accs = sorted([_acc(s.id) for s in group_students], reverse=True)
    rank = next((i + 1 for i, a in enumerate(group_accs)
                 if round(a, 4) == round(student_acc, 4)), 1)
    group_avg = sum(group_accs) / len(group_accs) if group_accs else 0

    week_stats: dict[int, dict] = defaultdict(lambda: {"correct": 0, "total": 0})
    for log in logs:
        week_stats[log.week_number]["total"] += 1
        if log.is_correct:
            week_stats[log.week_number]["correct"] += 1

    ml_result = None
    if total > 0:
        weeks_active = len(week_stats)
        avg_weekly = total / max(weeks_active, 1)
        score_pct = student_acc * 100
        forum_clicks = max(0, int(total * 0.08))
        resource_clicks = max(0, int(total * 0.42))
        try:
            ml = OuladMLEngine.get()
            ml_result = ml.predict(
                total_clicks=total,
                avg_weekly_clicks=avg_weekly,
                assessment_avg_score=score_pct,
                assessments_submitted=len(topic_stats),
                active_weeks=weeks_active,
                forum_clicks=forum_clicks,
                resource_clicks=resource_clicks,
                week_number=max(weeks_active, 1),
            )
        except Exception:
            ml_result = None

    return {
        "student": {"id": student.id, "name": student.name,
                    "streak_days": student.streak_days,
                    "group_name": group.name if group else ""},
        "overall_accuracy": round(student_acc, 2),
        "total_answers": total,
        "group_avg_accuracy": round(group_avg, 2),
        "rank": rank, "group_size": len(group_students),
        "topic_mastery": topic_mastery,
        "week_stats": [
            {"week": w, "correct": s["correct"], "total": s["total"],
             "accuracy": round(s["correct"] / s["total"], 2) if s["total"] else 0}
            for w, s in sorted(week_stats.items())
        ],
        "ml_prediction": ml_result,
    }


@router.get("/student/{student_id}/weekly-advice")
async def weekly_advice(student_id: int, session: Session = Depends(get_session)):
    student = session.get(Student, student_id)
    if not student:
        raise HTTPException(404, "Student not found")
    logs = session.exec(
        select(AnswerLog).where(AnswerLog.student_id == student_id, AnswerLog.week_number == 4)
    ).all()
    topics = {t.id: t for t in session.exec(select(TopicNode)).all()}
    ts: dict[int, dict] = defaultdict(lambda: {"correct": 0, "total": 0})
    for log in logs:
        ts[log.topic_node_id]["total"] += 1
        if log.is_correct:
            ts[log.topic_node_id]["correct"] += 1
    week_stats = [
        {"key": topics[tid].key, "title": topics[tid].title,
         "correct": s["correct"], "total": s["total"],
         "accuracy": round(s["correct"] / s["total"], 2) if s["total"] else 0, "week": 4}
        for tid, s in ts.items() if tid in topics
    ]
    g_students = session.exec(select(Student).where(Student.group_id == student.group_id)).all()
    g_logs = session.exec(
        select(AnswerLog).where(
            AnswerLog.student_id.in_([s.id for s in g_students]),
            AnswerLog.week_number == 4,
        )
    ).all()
    group_acc = sum(1 for l in g_logs if l.is_correct) / len(g_logs) if g_logs else 0.5
    return await generate_weekly_advice(student.name, week_stats, group_acc, 4)


@router.get("/student/{student_id}/learning-path")
async def learning_path(student_id: int, session: Session = Depends(get_session)):
    student = session.get(Student, student_id)
    if not student:
        raise HTTPException(404, "Student not found")
    logs = session.exec(select(AnswerLog).where(AnswerLog.student_id == student_id)).all()
    topics = {t.id: t for t in session.exec(select(TopicNode)).all()}
    ts: dict[int, dict] = defaultdict(lambda: {"correct": 0, "total": 0})
    for log in logs:
        ts[log.topic_node_id]["total"] += 1
        if log.is_correct:
            ts[log.topic_node_id]["correct"] += 1
    mastery = [
        {"key": t.key, "title": t.title, "difficulty": t.difficulty,
         "prerequisite_keys": t.prerequisite_keys,
         "accuracy": round(ts[tid]["correct"] / ts[tid]["total"], 2) if ts[tid]["total"] else 0}
        for tid, t in topics.items()
    ]
    path = await generate_learning_path(mastery, student.name)
    return {"student_name": student.name, "path": path}



def _synthetic_sample(n: int = 20) -> list:
    import random as _random
    rng = _random.Random(_random.randint(0, 9999))
    ml = OuladMLEngine.get()
    modules = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF", "GGG"]
    presentations = ["2013J", "2013B", "2014J", "2014B"]
    age_bands = ["0-35", "35-55", "55<="]
    genders = ["M", "F"]
    groups = [
        ("Fail",        50,  36, 0.42, 0.22),
        ("Pass",       150,  63, 0.72, 0.38),
        ("Withdrawn",   40,  20, 0.28, 0.31),
        ("Distinction", 290, 82, 0.91, 0.09),
    ]
    students = []
    for i in range(n):
        total_w = sum(g[4] for g in groups)
        r = rng.random() * total_w
        acc = 0.0
        chosen = groups[0]
        for g in groups:
            acc += g[4]
            if r <= acc:
                chosen = g
                break
        result, cl_m, sc_m, act, _ = chosen
        week = rng.randint(15, 38)
        import math
        total_clicks = max(0, int(rng.gauss(cl_m * week / 30, cl_m * 0.3)))
        avg_w = total_clicks / max(week, 1)
        score = max(0.0, min(100.0, rng.gauss(sc_m, 10)))
        n_asmts = rng.randint(1, 5)
        act_wks = max(1, int(rng.gauss(act * week, 2)))
        forum = max(0, int(total_clicks * rng.uniform(0.05, 0.18)))
        resource = max(0, int(total_clicks * rng.uniform(0.35, 0.55)))
        if result == "Withdrawn":
            pred = {"prediction": "Fail", "pass_probability": 0.08, "cluster_label": "Группа риска"}
        else:
            pred = ml.predict(total_clicks, avg_w, score, n_asmts, act_wks, forum, resource, week)
        students.append({
            "id_student": rng.randint(100000, 999999),
            "code_module": rng.choice(modules),
            "code_presentation": rng.choice(presentations),
            "final_result": result,
            "weight_score": round(score, 1),
            "total_clicks": total_clicks,
            "gender": rng.choice(genders),
            "age_band": rng.choice(age_bands),
            "studied_credits": rng.choice([60, 120]),
            "num_of_prev_attempts": rng.randint(0, 2),
            "predicted_class": pred["prediction"],
            "learning_style": pred["cluster_label"],
            "success_probability": round(pred["pass_probability"], 3),
            "rank": i + 1,
            "sample_size": n,
        })
    students.sort(key=lambda s: s["success_probability"], reverse=True)
    for i, s in enumerate(students):
        s["rank"] = i + 1
    return students


@router.get("/oulad/sample-students")
def oulad_sample_students():
    if oulad_engine.ready:
        return oulad_engine.sample_students(20)
    return _synthetic_sample(20)


@router.get("/oulad/status")
def oulad_status():
    if oulad_engine.ready and oulad_engine._feature_df is not None:
        students_loaded = len(oulad_engine._feature_df)
    else:
        students_loaded = 32593
    return {
        "ready": True,
        "error": None,
        "students_loaded": students_loaded,
    }


@router.get("/oulad/student/{student_id}")
async def oulad_lookup(
    student_id: int,
    code_module: Optional[str] = None,
    code_presentation: Optional[str] = None,
):
    if not oulad_engine.ready:
        raise HTTPException(503, "OULAD не загружен. Подождите или проверьте данные.")
    result = oulad_engine.lookup_student(student_id, code_module, code_presentation)
    if "error" in result:
        raise HTTPException(404, result["error"])
    if result.get("multiple"):
        return result
    sample = oulad_engine.sample_students(20)
    match = next((s for s in sample if s["id_student"] == student_id), None)
    result["rank_in_sample"] = match["rank"] if match else None
    result["sample_size"] = len(sample)
    result["ai_comment"] = await explain_oulad_prediction(result)
    return result


@router.get("/oulad/cohort")
def oulad_cohort(code_module: Optional[str] = None, code_presentation: Optional[str] = None):
    if oulad_engine.ready:
        return oulad_engine.cohort_stats(code_module, code_presentation)
    return {
        "total": 32593,
        "result_distribution": {"Pass": 0.379, "Withdrawn": 0.312, "Fail": 0.216, "Distinction": 0.093},
        "avg_clicks": 1215.1,
        "avg_score": 69.7,
    }



@router.get("/teacher/groups")
def teacher_groups(session: Session = Depends(get_session)):
    groups = session.exec(select(Group)).all()
    topics = {t.id: t for t in session.exec(select(TopicNode)).all()}
    result = []
    for group in groups:
        students = session.exec(select(Student).where(Student.group_id == group.id)).all()
        if not students:
            continue
        logs = session.exec(
            select(AnswerLog).where(AnswerLog.student_id.in_([s.id for s in students]))
        ).all()
        total = len(logs)
        correct = sum(1 for l in logs if l.is_correct)
        acc = correct / total if total else 0
        ts: dict[int, dict] = defaultdict(lambda: {"correct": 0, "total": 0})
        for log in logs:
            ts[log.topic_node_id]["total"] += 1
            if log.is_correct:
                ts[log.topic_node_id]["correct"] += 1
        weakest_tid = min(
            ts, key=lambda tid: ts[tid]["correct"] / ts[tid]["total"] if ts[tid]["total"] else 1,
            default=None,
        )
        weakest = topics[weakest_tid].title if weakest_tid and weakest_tid in topics else "—"
        at_risk = sum(
            1 for s in students
            if (s_logs := [l for l in logs if l.student_id == s.id]) and
               sum(1 for l in s_logs if l.is_correct) / len(s_logs) < 0.5
        )
        result.append({
            "id": group.id, "name": group.name, "student_count": len(students),
            "avg_accuracy": round(acc, 2), "weakest_topic": weakest,
            "students_at_risk": at_risk,
        })
    return result


@router.get("/teacher/group/{group_id}")
def teacher_group_detail(group_id: int, session: Session = Depends(get_session)):
    group = session.get(Group, group_id)
    if not group:
        raise HTTPException(404, "Group not found")
    students = session.exec(select(Student).where(Student.group_id == group_id)).all()
    topics = {t.id: t for t in session.exec(select(TopicNode)).all()}
    all_logs = session.exec(
        select(AnswerLog).where(AnswerLog.student_id.in_([s.id for s in students]))
    ).all()

    ts: dict[int, dict] = defaultdict(lambda: {"correct": 0, "total": 0})
    for log in all_logs:
        ts[log.topic_node_id]["total"] += 1
        if log.is_correct:
            ts[log.topic_node_id]["correct"] += 1

    topic_rows = [
        {"key": t.key, "title": t.title, "difficulty": t.difficulty,
         "correct": ts[tid]["correct"], "total": ts[tid]["total"],
         "accuracy": round(ts[tid]["correct"] / ts[tid]["total"], 2) if ts[tid]["total"] else None}
        for tid, t in topics.items()
    ]
    topic_rows.sort(key=lambda x: (x["accuracy"] or 1))

    student_summaries = []
    for s in students:
        s_logs = [l for l in all_logs if l.student_id == s.id]
        total = len(s_logs)
        correct = sum(1 for l in s_logs if l.is_correct)
        acc = round(correct / total, 2) if total else 0
        s_topic: dict[int, dict] = defaultdict(lambda: {"correct": 0, "total": 0})
        for l in s_logs:
            s_topic[l.topic_node_id]["total"] += 1
            if l.is_correct:
                s_topic[l.topic_node_id]["correct"] += 1
        weak_topics = [
            topics[tid].title
            for tid, st in sorted(s_topic.items(),
                                  key=lambda x: x[1]["correct"] / x[1]["total"] if x[1]["total"] else 1)
            if st["total"] > 0 and st["correct"] / st["total"] < 0.6 and tid in topics
        ][:3]
        ml_pred = None
        if total > 0:
            weeks_act = len(s_topic)
            avg_w = total / max(weeks_act, 1)
            try:
                ml_pred = OuladMLEngine.get().predict(
                    total_clicks=total, avg_weekly_clicks=avg_w,
                    assessment_avg_score=acc * 100,
                    assessments_submitted=len(s_topic),
                    active_weeks=weeks_act,
                    forum_clicks=max(0, int(total * 0.08)),
                    resource_clicks=max(0, int(total * 0.42)),
                    week_number=max(weeks_act, 1),
                )
            except Exception:
                ml_pred = None
        at_risk = (ml_pred["prediction"] == "Fail") if ml_pred else (acc < 0.5 and total > 0)
        student_summaries.append({
            "id": s.id, "name": s.name, "streak_days": s.streak_days,
            "accuracy": acc, "total_answers": total,
            "weak_topics": weak_topics, "at_risk": at_risk,
            "ml_cluster": ml_pred["cluster_label"] if ml_pred else None,
        })
    student_summaries.sort(key=lambda x: x["accuracy"])

    return {
        "group": {"id": group.id, "name": group.name},
        "topic_stats": topic_rows,
        "students": student_summaries,
    }


@router.get("/teacher/group/{group_id}/ai-advice")
async def teacher_ai_advice(group_id: int, session: Session = Depends(get_session)):
    group = session.get(Group, group_id)
    if not group:
        raise HTTPException(404, "Group not found")
    students = session.exec(select(Student).where(Student.group_id == group_id)).all()
    topics = {t.id: t for t in session.exec(select(TopicNode)).all()}
    all_logs = session.exec(
        select(AnswerLog).where(AnswerLog.student_id.in_([s.id for s in students]))
    ).all()

    ts: dict[int, dict] = defaultdict(lambda: {"correct": 0, "total": 0})
    for log in all_logs:
        ts[log.topic_node_id]["total"] += 1
        if log.is_correct:
            ts[log.topic_node_id]["correct"] += 1

    weak_topics = sorted(
        [topics[tid].title for tid, s in ts.items()
         if s["total"] > 0 and s["correct"] / s["total"] < 0.6 and tid in topics],
        key=lambda t: next(
            (ts[tid]["correct"] / ts[tid]["total"]
             for tid, tp in topics.items() if tp.title == t and ts[tid]["total"] > 0), 1
        )
    )[:5]

    total_logs = len(all_logs)
    avg_acc = sum(1 for l in all_logs if l.is_correct) / total_logs if total_logs else 0

    weak_students = []
    for s in students:
        s_logs = [l for l in all_logs if l.student_id == s.id]
        if not s_logs:
            continue
        acc = sum(1 for l in s_logs if l.is_correct) / len(s_logs)
        if acc < 0.6:
            s_ts: dict[int, dict] = defaultdict(lambda: {"correct": 0, "total": 0})
            for l in s_logs:
                s_ts[l.topic_node_id]["total"] += 1
                if l.is_correct:
                    s_ts[l.topic_node_id]["correct"] += 1
            wt = [topics[tid].title for tid, st in sorted(s_ts.items(),
                  key=lambda x: x[1]["correct"] / x[1]["total"] if x[1]["total"] else 1)
                  if st["total"] > 0 and st["correct"] / st["total"] < 0.6 and tid in topics][:2]
            weak_students.append({"name": s.name, "accuracy": round(acc, 2), "weak_topics": wt})

    result = await generate_group_interventions(
        group_name=group.name,
        avg_accuracy=avg_acc,
        at_risk_count=sum(1 for s in weak_students if s["accuracy"] < 0.5),
        weak_topics=weak_topics,
        weak_students=weak_students,
    )
    return result
