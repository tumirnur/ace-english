import json
import os
from app.core.config import settings

ERROR_TO_PREREQ: dict[str, str | None] = {
    "third_person_s": "subject_verb", "plural_agreement": "subject_verb",
    "negative_form": "present_simple", "question_form": "present_simple",
    "word_order": "present_simple", "past_form": "irregular_verbs",
    "past_participle": "irregular_verbs", "auxiliary_be": "present_simple",
    "continuous_negation": "present_continuous", "ing_form": "present_simple",
    "regular_ed": "present_simple", "past_negative": "past_simple",
    "past_question": "past_simple", "will_prediction": "present_simple",
    "will_spontaneous": "present_simple", "going_to_plan": "present_continuous",
    "going_to_evidence": "present_continuous", "pp_vs_past": "past_simple",
    "pp_with_ever": "irregular_verbs", "pp_with_just": "irregular_verbs",
    "past_cont_interrupted": "present_continuous", "past_cont_parallel": "present_continuous",
    "pp_sequence": "present_perfect", "pp_before": "present_perfect",
    "ppc_duration": "present_perfect", "ppc_since_for": "present_perfect",
}

FALLBACK_EXPLANATIONS: dict[str, str] = {
    "third_person_s": "Глагол в 3-м лице ед.ч. требует окончания -s/-es (she goes).",
    "plural_agreement": "С множественным числом используется форма 'are'.",
    "negative_form": "В отрицании Present Simple: don't/doesn't + инфинитив без -s.",
    "question_form": "В вопросе Present Simple нужен вспомогательный do/does.",
    "word_order": "Наречие частотности ставится перед смысловым глаголом.",
    "past_form": "Это неправильный глагол — форма прошедшего не через -ed.",
    "past_participle": "Нужна форма III (Past Participle), отличная от простого прошлого.",
    "auxiliary_be": "Present Continuous: am/is/are + глагол с -ing.",
    "continuous_negation": "Отрицание Continuous: am/is/are + not + -ing.",
    "ing_form": "В Present Continuous нужен вспомогательный be + -ing.",
    "regular_ed": "Правильные глаголы в Past Simple получают -ed.",
    "past_negative": "Отрицание Past Simple: didn't + инфинитив (без -ed!).",
    "past_question": "Вопрос Past Simple: Did + подлежащее + инфинитив.",
    "will_prediction": "Для предсказаний используется will + инфинитив.",
    "will_spontaneous": "Для спонтанных решений в момент речи — will.",
    "going_to_plan": "Для заранее принятых планов — be going to.",
    "going_to_evidence": "При видимых признаках события — be going to.",
    "pp_vs_past": "Present Perfect (have/has + III форма) — связь с настоящим.",
    "pp_with_ever": "После 'ever' нужна III форма (Past Participle).",
    "pp_with_just": "После just в Present Perfect — III форма.",
    "past_cont_interrupted": "Past Continuous (was/were + -ing) — фоновое действие.",
    "past_cont_parallel": "Два параллельных действия в прошлом — оба Past Continuous.",
    "pp_sequence": "Past Perfect (had + III форма) — действие до другого прошлого момента.",
    "pp_before": "Had + III форма — действие произошло раньше другого.",
    "ppc_duration": "Present Perfect Continuous (have/has been + -ing) — длящийся процесс.",
    "ppc_since_for": "Has been + -ing с since/for — процесс от прошлого до сейчас.",
}

_MODEL = "claude-haiku-4-5-20251001"


def _api_key() -> str:
    return settings.llm_api_key or os.environ.get("LLM_API_KEY", "")


async def _request(prompt: str, max_tokens: int = 400) -> str:
    from anthropic import AsyncAnthropic
    client = AsyncAnthropic(api_key=_api_key())
    resp = await client.messages.create(
        model=_MODEL,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text.strip()


async def _request_json(prompt: str, max_tokens: int = 400) -> dict:
    try:
        text = await _request(prompt, max_tokens)
        text = text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text.strip())
    except Exception:
        return {}


async def analyze_error(
    question_text: str,
    student_answer: str,
    correct_answer: str,
    current_topic_title: str,
    error_category: str,
    prerequisite_nodes: list[dict],
) -> dict:
    if _api_key():
        prereqs = "\n".join(f"- key={n['key']}, title={n['title']}" for n in prerequisite_nodes)
        prompt = (
            f"You are an English grammar tutor. A student made an error.\n"
            f"Current topic: {current_topic_title}\n"
            f"Question: {question_text}\n"
            f"Student answered: \"{student_answer}\"\n"
            f"Correct answer: \"{correct_answer}\"\n"
            f"Prerequisite topics:\n{prereqs}\n\n"
            f"Identify the specific grammatical problem. "
            f"Respond ONLY with JSON:\n"
            f'{{"problem":"<объяснение ошибки на русском, 1-2 предложения>",'
            f'"target_node_key":"<key одного из prerequisites или null>",'
            f'"redirect_reason":"<почему именно эта тема, 1 предложение>"}}'
        )
        result = await _request_json(prompt, 300)
        if result.get("problem"):
            return result

    target_key = ERROR_TO_PREREQ.get(error_category)
    prereq_keys = {n["key"] for n in prerequisite_nodes}
    if target_key and target_key not in prereq_keys:
        target_key = None
    target_node = next((n for n in prerequisite_nodes if n["key"] == target_key), None)
    return {
        "problem": FALLBACK_EXPLANATIONS.get(error_category, "Повторите базовые правила этой темы."),
        "target_node_key": target_key,
        "redirect_reason": (f"Ошибка связана с темой «{target_node['title']}»."
                            if target_node else "Рекомендуем повторить текущую тему."),
    }


async def generate_hint(
    question_text: str,
    topic_title: str,
    options: list[str],
    error_category: str,
) -> str:
    if _api_key():
        opts = ", ".join(f'"{o}"' for o in options)
        prompt = (
            f"English grammar topic: {topic_title}\n"
            f"Question: {question_text}\n"
            f"Options: {opts}\n\n"
            f"Give a helpful hint in Russian (2-3 sentences) that helps the student think through "
            f"the answer WITHOUT revealing it. Focus on the grammar rule, not the answer itself."
        )
        try:
            return await _request(prompt, 200)
        except Exception:
            pass

    return FALLBACK_EXPLANATIONS.get(
        error_category,
        f"Вспомни правило темы «{topic_title}». Обрати внимание на подлежащее и форму глагола."
    )


async def analyze_session_gaps(
    errors: list[dict],
    student_name: str,
) -> dict:
    if not errors:
        return {"gaps": [], "summary": "Ошибок в сессии нет.", "recommendation": ""}

    if _api_key():
        errors_text = "\n".join(
            f"- Тема «{e.get('topic_title', e.get('topic', '?'))}», "
            f"категория: {e.get('error_category', '?')}"
            + (f", вопрос: {e['question_text'][:60]}" if e.get('question_text') else "")
            + (f", ответил: {e['student_answer']}" if e.get('student_answer') else "")
            for e in errors
        )
        prompt = (
            f"Студент {student_name} допустил ошибки за сессию:\n{errors_text}\n\n"
            f"Найди системные паттерны и корневые причины ошибок. "
            f"Ответь ТОЛЬКО JSON:\n"
            f'{{"gaps":[{{"topic":"...","problem":"...","priority":"high/medium/low"}}],'
            f'"summary":"<общая картина, 2 предложения>",'
            f'"recommendation":"<что делать в первую очередь, 1-2 предложения>"}}'
        )
        result = await _request_json(prompt, 500)
        if result.get("summary"):
            return result

    topics = list({e.get("topic_title", e.get("topic", "?")) for e in errors})
    return {
        "gaps": [{"topic": t, "problem": "Требует повторения", "priority": "medium"} for t in topics],
        "summary": f"Выявлено {len(errors)} ошибок в {len(topics)} темах.",
        "recommendation": f"Начни с повторения: {topics[0]}." if topics else "",
    }


async def generate_learning_path(
    mastery: list[dict],
    student_name: str,
) -> list[dict]:
    sorted_m = sorted(mastery, key=lambda x: (x["accuracy"], -x["difficulty"]))

    if _api_key():
        mastery_text = "\n".join(
            f"- {m['title']}: {int(m['accuracy']*100)}% правильных, сложность {m['difficulty']}/4, "
            f"пред-темы: {m.get('prerequisite_keys', [])}"
            for m in mastery
        )
        prompt = (
            f"Студент {student_name} изучает английские времена глагола.\n"
            f"Текущий прогресс:\n{mastery_text}\n\n"
            f"Составь оптимальный персональный путь (порядок тем для изучения) "
            f"с учётом зависимостей и текущего уровня. "
            f"Ответь ТОЛЬКО JSON — массив:\n"
            f'[{{"key":"...","title":"...","reason":"<почему сейчас эта тема, 1 предложение>",'
            f'"estimated_sessions":1}}]'
        )
        result = await _request_json(prompt, 600)
        if isinstance(result, list) and result:
            return result

    return [
        {"key": m["key"], "title": m["title"],
         "reason": "Низкая точность — требует повторения." if m["accuracy"] < 0.6 else "Закрепление.",
         "estimated_sessions": max(1, int((1 - m["accuracy"]) * 4))}
        for m in sorted_m if m["accuracy"] < 0.8
    ][:8]


async def generate_weekly_advice(
    student_name: str,
    week_stats: list[dict],
    group_avg_accuracy: float,
    current_week: int,
) -> dict:
    if _api_key():
        stats_text = "\n".join(
            f"- {s['title']}: {s['correct']}/{s['total']} ({int(s['accuracy']*100)}%)"
            for s in week_stats
        )
        prompt = (
            f"Ты — тьютор по английской грамматике. Студент: {student_name}.\n"
            f"Неделя {current_week}, статистика:\n{stats_text}\n"
            f"Средняя по группе: {int(group_avg_accuracy*100)}%\n\n"
            f"Напиши персональный совет. Ответь ТОЛЬКО JSON:\n"
            f'{{"advice":"<2-3 предложения>","focus_topics":["..."],'
            f'"forecast":"<1 предложение>","motivation":"<мотивирующая фраза>"}}'
        )
        result = await _request_json(prompt, 400)
        if result.get("advice"):
            return result

    weak = [s for s in week_stats if s["accuracy"] < 0.6]
    focus = [s["title"] for s in sorted(weak, key=lambda x: x["accuracy"])[:2]]
    avg = sum(s["accuracy"] for s in week_stats) / len(week_stats) if week_stats else 0
    if avg >= group_avg_accuracy + 0.1:
        advice = "Ты опережаешь группу — отличный прогресс! Переходи к более сложным временам."
        motivation = "Продолжай в том же темпе!"
    elif avg < group_avg_accuracy - 0.1:
        advice = "Есть темы, которые стоит подтянуть. Уделяй по 15 минут в день слабым темам."
        motivation = "Каждая ошибка — шаг к знанию!"
    else:
        advice = "Ты идёшь в ногу с группой. Сосредоточься на темах ниже 60% правильных."
        motivation = "Стабильность — залог успеха!"
    weeks_left = max(1, 4 - current_week)
    return {"advice": advice, "focus_topics": focus,
            "forecast": f"При текущем темпе завершишь курс через ~{weeks_left} недели.",
            "motivation": motivation}


async def explain_oulad_prediction(
    student_data: dict,
) -> str:
    prob = student_data.get("success_probability", 0)
    cluster = student_data.get("learning_style", "")
    predicted = student_data.get("predicted_class", "")
    clicks = student_data.get("total_clicks", 0)
    score = student_data.get("weight_score")
    actual = student_data.get("final_result_known", "")

    if _api_key():
        prompt = (
            f"Объясни результат ML-анализа студента OULAD на русском языке (2-3 предложения):\n"
            f"- Прогноз: {predicted} (вероятность успеха {int(prob*100)}%)\n"
            f"- Поведенческий кластер: {cluster}\n"
            f"- Кликов по курсу: {clicks}\n"
            f"- Средний балл: {f'{score:.1f}' if score else 'нет данных'}\n"
            f"- Реальный итог в таблице: {actual}\n\n"
            f"Объясни простыми словами что это значит для студента. "
            f"Если прогноз совпал с реальным — отметь это. Не используй markdown."
        )
        try:
            return await _request(prompt, 250)
        except Exception:
            pass

    match_text = f" Прогноз {'совпал' if predicted == actual else 'не совпал'} с реальным итогом ({actual})." if actual and actual != "?" else ""
    cluster_map = {"Активные": "активно работал с материалами", "Результативные": "показал хорошие результаты при умеренной активности", "Группа риска": "показал признаки риска по активности и баллам"}
    cluster_ru = cluster_map.get(cluster, cluster)
    return (f"Модель предсказывает исход «{predicted}» с вероятностью успеха {int(prob*100)}%. "
            f"По поведению студент {cluster_ru}.{match_text}")


async def generate_group_interventions(
    group_name: str,
    avg_accuracy: float,
    at_risk_count: int,
    weak_topics: list[str],
    weak_students: list[dict],
) -> dict:
    if _api_key():
        weak_s = "\n".join(f"- {s['name']}: точность {int(s['accuracy']*100)}%, слабые темы: {', '.join(s['weak_topics'][:2])}"
                           for s in weak_students[:5])
        prompt = (
            f"Ты — методист. Группа {group_name}, средняя точность {int(avg_accuracy*100)}%, "
            f"{at_risk_count} студентов в зоне риска.\n"
            f"Слабейшие темы: {', '.join(weak_topics[:4])}.\n"
            f"Студенты требующие внимания:\n{weak_s}\n\n"
            f"Составь план интервенций. Ответь ТОЛЬКО JSON:\n"
            f'{{"interventions":[{{"priority":"high/medium","action":"...","target":"...","rationale":"..."}}],'
            f'"overall_strategy":"<2 предложения>","time_estimate":"<например: 2 недели>"}}'
        )
        result = await _request_json(prompt, 600)
        if result.get("interventions"):
            return result

    return {
        "interventions": [
            {"priority": "high", "action": f"Повторить тему «{t}»",
             "target": "вся группа", "rationale": "Низкая точность по теме"}
            for t in weak_topics[:3]
        ],
        "overall_strategy": f"Группа {group_name} требует дополнительных занятий по слабым темам.",
        "time_estimate": "1-2 недели",
    }
