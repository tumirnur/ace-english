import random
from datetime import datetime, timedelta

from sqlmodel import Session, select

from app.db.models import AnswerLog, Group, Question, Student, TopicNode

TOPIC_NODES = [
    {
        "key": "subject_verb",
        "title": "Подлежащее и сказуемое",
        "description": "Согласование подлежащего со сказуемым (he goes / they go)",
        "theory": (
            "В английском предложении строгий порядок слов: Подлежащее (Subject) + Сказуемое (Verb) + Дополнение. "
            "Подлежащее отвечает на вопрос «кто? что?», сказуемое — «что делает?». "
            "Глагол должен согласовываться с подлежащим: единственное число — he/she/it goes; "
            "множественное — they go. Без подлежащего предложение невозможно даже в командах "
            "(там подразумевается You: «Go!» = «You go!»)."
        ),
        "difficulty": 1,
        "prerequisite_keys": [],
        "pos_x": 250, "pos_y": 58,
    },
    {
        "key": "present_simple",
        "title": "Present Simple",
        "description": "Настоящее простое — факты, привычки, расписание",
        "theory": (
            "Present Simple описывает регулярные действия, постоянные факты и расписания. "
            "Форма: base verb (I/you/we/they go), для 3-го лица ед.ч. добавляй -s/-es (he goes, she watches). "
            "Отрицание: don't / doesn't + инфинитив. Вопрос: Do/Does + subject + verb? "
            "Маркеры: always, usually, often, sometimes, never, every day/week."
        ),
        "difficulty": 1,
        "prerequisite_keys": ["subject_verb"],
        "pos_x": 250, "pos_y": 175,
    },
    {
        "key": "irregular_verbs",
        "title": "Неправильные глаголы",
        "description": "Формы неправильных глаголов: go→went→gone, see→saw→seen",
        "theory": (
            "Неправильные глаголы не образуют Past Simple добавлением -ed. Нужно знать три формы: "
            "Infinitive → Past Simple → Past Participle. "
            "Примеры: go→went→gone, see→saw→seen, take→took→taken, write→wrote→written, "
            "have→had→had, do→did→done, be→was/were→been. "
            "Past Participle (3-я форма) нужна для Perfect времён и пассивного залога."
        ),
        "difficulty": 2,
        "prerequisite_keys": ["present_simple"],
        "pos_x": 100, "pos_y": 305,
    },
    {
        "key": "present_continuous",
        "title": "Present Continuous",
        "description": "Настоящее длительное — действие происходит прямо сейчас",
        "theory": (
            "Present Continuous используется для действий, происходящих прямо сейчас или временно в этот период. "
            "Формула: am/is/are + глагол-ing. "
            "She is reading. They are working this week. "
            "Важно: нельзя использовать с глаголами состояния (state verbs): know, like, want, need, believe, understand. "
            "Маркеры: now, right now, at the moment, currently, this week/month."
        ),
        "difficulty": 2,
        "prerequisite_keys": ["present_simple"],
        "pos_x": 250, "pos_y": 305,
    },
    {
        "key": "future_will",
        "title": "Future Simple (will)",
        "description": "Будущее время с will — решения и предсказания",
        "theory": (
            "Future Simple с will — для спонтанных решений, обещаний и предсказаний. "
            "Формула: will + инфинитив для всех лиц (I/you/he/she/they will go). "
            "Отрицание: won't (will not). Вопрос: Will + subject + verb? "
            "Когда использовать: решение принято прямо сейчас («I'll help you»), "
            "обещание («I will call you»), предсказание без доказательств («It will rain»). "
            "Маркеры: tomorrow, next week, probably, I think, I'm sure."
        ),
        "difficulty": 2,
        "prerequisite_keys": ["present_simple"],
        "pos_x": 400, "pos_y": 305,
    },
    {
        "key": "past_simple",
        "title": "Past Simple",
        "description": "Прошедшее простое — завершённые действия в прошлом",
        "theory": (
            "Past Simple — для завершённых действий в прошлом в конкретный момент. "
            "Правильные глаголы: base + ed (worked, played, visited). "
            "Неправильные: вторая форма (went, saw, took). "
            "Отрицание: didn't + инфинитив (She didn't go). "
            "Вопрос: Did + subject + infinitive? (Did you see it?) "
            "Маркеры: yesterday, last week/year, ago, in 2020, when."
        ),
        "difficulty": 2,
        "prerequisite_keys": ["present_simple", "irregular_verbs"],
        "pos_x": 130, "pos_y": 435,
    },
    {
        "key": "future_going_to",
        "title": "Future (going to)",
        "description": "Будущее с be going to — планы и намерения",
        "theory": (
            "Future (going to) — для уже запланированных намерений и предсказаний с очевидными признаками. "
            "Формула: am/is/are + going to + инфинитив. "
            "I am going to study medicine (запланировано). Look at those clouds — it's going to rain (видим доказательства). "
            "Отличие от will: going to = решение принято заранее, will = решение прямо сейчас. "
            "Маркеры: tonight, next month, soon, I've decided to, I'm planning to."
        ),
        "difficulty": 2,
        "prerequisite_keys": ["present_continuous"],
        "pos_x": 370, "pos_y": 435,
    },
    {
        "key": "present_perfect",
        "title": "Present Perfect",
        "description": "Настоящее совершённое — опыт, результат, связь с настоящим",
        "theory": (
            "Present Perfect связывает прошлое с настоящим: опыт, изменения, незавершённое действие. "
            "Формула: have/has + Past Participle (3-я форма). "
            "I have visited Paris (опыт). She has just arrived (только что). He hasn't finished yet (ещё не). "
            "Никогда не используй с конкретным временем (yesterday, in 2020 → Past Simple). "
            "Маркеры: already, yet, ever, never, just, recently, so far, since, for."
        ),
        "difficulty": 3,
        "prerequisite_keys": ["past_simple", "irregular_verbs"],
        "pos_x": 100, "pos_y": 565,
    },
    {
        "key": "past_continuous",
        "title": "Past Continuous",
        "description": "Прошедшее длительное — действие в момент другого события",
        "theory": (
            "Past Continuous — для длящегося действия в определённый момент прошлого "
            "или фона для другого (внезапного) события. "
            "Формула: was/were + глагол-ing. "
            "I was sleeping at 10pm (в этот момент). "
            "While I was reading, he called (фон + внезапное событие). "
            "Два параллельных: She was cooking while he was watching TV. "
            "Маркеры: while, when, at 7 o'clock yesterday, all morning."
        ),
        "difficulty": 3,
        "prerequisite_keys": ["present_continuous", "past_simple"],
        "pos_x": 340, "pos_y": 565,
    },
    {
        "key": "past_perfect",
        "title": "Past Perfect",
        "description": "Прошедшее совершённое — действие до другого прошлого момента",
        "theory": (
            "Past Perfect — для действия, которое завершилось раньше другого прошлого события. "
            "Формула: had + Past Participle (3-я форма) для всех лиц. "
            "He had left before she arrived (ушёл раньше, чем она пришла). "
            "I hadn't eaten, so I was hungry. "
            "Как ориентир: если в предложении два прошлых действия — более раннее в Past Perfect. "
            "Маркеры: before, after, by the time, already, just, when, because."
        ),
        "difficulty": 4,
        "prerequisite_keys": ["present_perfect"],
        "pos_x": 100, "pos_y": 695,
    },
    {
        "key": "present_perfect_cont",
        "title": "Present Perfect Continuous",
        "description": "Совершённое длительное — процесс с акцентом на продолжительность",
        "theory": (
            "Present Perfect Continuous — для действия, начавшегося в прошлом и продолжающегося сейчас "
            "(или только что закончившегося), с акцентом на длительность. "
            "Формула: have/has + been + глагол-ing. "
            "She has been studying for 3 hours (всё ещё учится). "
            "I've been waiting since 9am. He's tired because he's been working all day. "
            "Отличие от Present Perfect: continuous акцентирует процесс, а не результат. "
            "Маркеры: for, since, how long, all day/morning."
        ),
        "difficulty": 4,
        "prerequisite_keys": ["present_perfect", "present_continuous"],
        "pos_x": 340, "pos_y": 695,
    },
]

QUESTIONS = [
    {
        "topic_key": "subject_verb", "error_category": "correlative_conjunction",
        "text": "Neither the professor nor the students ___ been informed of the examination format change.",
        "options": ["has", "have", "had", "were"],
        "correct_answer": "have",
    },
    {
        "topic_key": "subject_verb", "error_category": "collective_noun",
        "text": "The committee, along with several independent consultants, ___ currently reviewing the proposed amendments.",
        "options": ["are", "is", "were", "have been"],
        "correct_answer": "is",
    },
    {
        "topic_key": "subject_verb", "error_category": "quantifier_agreement",
        "text": "A number of critical issues ___ been raised during the parliamentary debate on climate legislation.",
        "options": ["has", "have", "was", "is"],
        "correct_answer": "have",
    },
    {
        "topic_key": "subject_verb", "error_category": "plural_agreement",
        "text": "Economics and political science ___ often studied together at postgraduate level.",
        "options": ["is", "are", "was", "has been"],
        "correct_answer": "are",
    },

    {
        "topic_key": "present_simple", "error_category": "academic_third_person",
        "text": "The research consistently ___ that regular aerobic exercise improves cognitive function in elderly populations.",
        "options": ["demonstrate", "demonstrates", "is demonstrating", "demonstrated"],
        "correct_answer": "demonstrates",
    },
    {
        "topic_key": "present_simple", "error_category": "plural_third_person",
        "text": "According to the marking criteria, examiners ___ compositions not only for accuracy but also for coherence and lexical range.",
        "options": ["assesses", "assess", "is assessing", "assessed"],
        "correct_answer": "assess",
    },
    {
        "topic_key": "present_simple", "error_category": "scientific_fact",
        "text": "The Gulf Stream ___ the climates of Western Europe considerably milder than they would otherwise be.",
        "options": ["make", "makes", "is making", "has made"],
        "correct_answer": "makes",
    },
    {
        "topic_key": "present_simple", "error_category": "negative_academic",
        "text": "The authors ___ not claim that their findings can be generalised beyond the original sample.",
        "options": ["does", "do", "did", "are"],
        "correct_answer": "do",
    },

    {
        "topic_key": "irregular_verbs", "error_category": "past_form",
        "text": "The stock market ___ dramatically in the weeks following the central bank's shock announcement.",
        "options": ["falled", "fell", "fallen", "has fallen"],
        "correct_answer": "fell",
    },
    {
        "topic_key": "irregular_verbs", "error_category": "past_participle",
        "text": "By the time the panel convened, the committee members had already ___ the preliminary report.",
        "options": ["readed", "red", "read", "have read"],
        "correct_answer": "read",
    },
    {
        "topic_key": "irregular_verbs", "error_category": "past_form",
        "text": "The archaeologists ___ several previously unknown artefacts during last summer's excavation.",
        "options": ["finded", "found", "have find", "finds"],
        "correct_answer": "found",
    },
    {
        "topic_key": "irregular_verbs", "error_category": "past_participle",
        "text": "Once they had ___ the full implications of the new legislation, investors began withdrawing capital.",
        "options": ["understand", "understood", "understandd", "understanding"],
        "correct_answer": "understood",
    },

    {
        "topic_key": "present_continuous", "error_category": "academic_ongoing",
        "text": "Scholars ___ increasingly examining how digital media reshapes public political discourse.",
        "options": ["are", "is", "do", "have"],
        "correct_answer": "are",
    },
    {
        "topic_key": "present_continuous", "error_category": "temporary_situation",
        "text": "The company ___ its recruitment strategy in response to shifting market demands this quarter.",
        "options": ["revises", "is revising", "revised", "has revised"],
        "correct_answer": "is revising",
    },
    {
        "topic_key": "present_continuous", "error_category": "state_verb_error",
        "text": "Which sentence is grammatically correct?",
        "options": [
            "She is knowing the answer to every question.",
            "They are understanding the legal implications.",
            "He is working on his doctoral thesis this semester.",
            "The policy is seeming overly restrictive.",
        ],
        "correct_answer": "He is working on his doctoral thesis this semester.",
    },
    {
        "topic_key": "present_continuous", "error_category": "ing_form",
        "text": "I ___ more and more convinced that this methodology contains a fundamental flaw.",
        "options": ["become", "am becoming", "became", "have become"],
        "correct_answer": "am becoming",
    },

    {
        "topic_key": "past_simple", "error_category": "regular_ed",
        "text": "The government ___ an emergency session last Tuesday to address the escalating economic crisis.",
        "options": ["convene", "convened", "has convened", "was convening"],
        "correct_answer": "convened",
    },
    {
        "topic_key": "past_simple", "error_category": "past_negative",
        "text": "The initial draft ___ meet the publication standards, so the editors requested substantial revisions.",
        "options": ["didn't", "doesn't", "hadn't", "wasn't"],
        "correct_answer": "didn't",
    },
    {
        "topic_key": "past_simple", "error_category": "past_question",
        "text": "___ the research team ___ the results before submitting the paper? (verify)",
        "options": ["Did / verified", "Did / verify", "Do / verified", "Have / verified"],
        "correct_answer": "Did / verify",
    },
    {
        "topic_key": "past_simple", "error_category": "past_vs_perfect",
        "text": "Darwin ___ his theory of evolution after years of meticulous observation aboard the Beagle.",
        "options": ["has developed", "developed", "develops", "was developing"],
        "correct_answer": "developed",
    },

    {
        "topic_key": "future_will", "error_category": "will_spontaneous",
        "text": "The server just crashed. Don't worry — I ___ contact technical support immediately.",
        "options": ["am going to", "will", "shall to", "am contacting"],
        "correct_answer": "will",
    },
    {
        "topic_key": "future_will", "error_category": "will_prediction",
        "text": "If deforestation continues at its current rate, scientists predict that the Amazon basin ___ lose half of its biodiversity by 2100.",
        "options": ["is going to", "will", "would", "shall"],
        "correct_answer": "will",
    },
    {
        "topic_key": "future_will", "error_category": "will_conditional",
        "text": "Unless stricter data-privacy regulations are enacted, companies ___ continue to exploit user data for targeted advertising.",
        "options": ["are going to", "will", "would", "shall"],
        "correct_answer": "will",
    },
    {
        "topic_key": "future_will", "error_category": "will_offer",
        "text": "You look overwhelmed with the statistics chapter — I ___ walk you through the regression analysis.",
        "options": ["am going to", "will", "am walking", "go to"],
        "correct_answer": "will",
    },

    {
        "topic_key": "future_going_to", "error_category": "going_to_plan",
        "text": "She has already booked flights and registered — she ___ present her research at the Oxford symposium in June.",
        "options": ["will", "is going to", "shall", "presents"],
        "correct_answer": "is going to",
    },
    {
        "topic_key": "future_going_to", "error_category": "going_to_evidence",
        "text": "Look at the patient's vital signs — his condition ___ deteriorate significantly without immediate intervention.",
        "options": ["will", "is going to", "would", "shall"],
        "correct_answer": "is going to",
    },
    {
        "topic_key": "future_going_to", "error_category": "going_to_intention",
        "text": "The government has signed the agreement and allocated the budget — they ___ invest £50 billion in railway expansion.",
        "options": ["will", "are going to", "shall", "invest"],
        "correct_answer": "are going to",
    },
    {
        "topic_key": "future_going_to", "error_category": "going_to_plan",
        "text": "I have enrolled in an intensive Mandarin course and selected my modules — I ___ focus on business vocabulary this semester.",
        "options": ["will", "am going to", "shall", "focus"],
        "correct_answer": "am going to",
    },

    {
        "topic_key": "present_perfect", "error_category": "pp_vs_past",
        "text": "The researchers ___ conclusively demonstrated the link between socioeconomic deprivation and reduced academic attainment.",
        "options": ["have", "had", "has", "did"],
        "correct_answer": "have",
    },
    {
        "topic_key": "present_perfect", "error_category": "pp_first_time",
        "text": "This is the first time the Security Council ___ voted unanimously on a resolution concerning climate change.",
        "options": ["has", "had", "have", "was"],
        "correct_answer": "has",
    },
    {
        "topic_key": "present_perfect", "error_category": "pp_since",
        "text": "The policy ___ been under review since the independent audit identified several critical regulatory gaps.",
        "options": ["has", "have", "had", "is"],
        "correct_answer": "has",
    },
    {
        "topic_key": "present_perfect", "error_category": "pp_vs_past",
        "text": "Significant advances in gene therapy ___ made it possible to treat previously incurable genetic disorders.",
        "options": ["have", "had", "has", "did"],
        "correct_answer": "have",
    },

    {
        "topic_key": "past_continuous", "error_category": "past_cont_interrupted",
        "text": "The witness stated that when the incident occurred, he ___ on the upper floor of the building.",
        "options": ["worked", "was working", "had worked", "has been working"],
        "correct_answer": "was working",
    },
    {
        "topic_key": "past_continuous", "error_category": "past_cont_background",
        "text": "While the parliamentary committee ___ the proposed budget, critics argued that the economic assumptions were flawed.",
        "options": ["examined", "was examining", "has examined", "had examined"],
        "correct_answer": "was examining",
    },
    {
        "topic_key": "past_continuous", "error_category": "past_cont_parallel",
        "text": "The data ___ being analysed when the server crashed, causing the loss of several weeks of research.",
        "options": ["is", "was", "has been", "had been"],
        "correct_answer": "was",
    },
    {
        "topic_key": "past_continuous", "error_category": "past_cont_parallel",
        "text": "At the time of the merger, the legal teams of both companies ___ separate confidentiality agreements.",
        "options": ["negotiated", "were negotiating", "have negotiated", "had negotiated"],
        "correct_answer": "were negotiating",
    },

    {
        "topic_key": "past_perfect", "error_category": "pp_sequence",
        "text": "By the time the court delivered its verdict, the defendant ___ over two years in custody.",
        "options": ["spent", "has spent", "had spent", "was spending"],
        "correct_answer": "had spent",
    },
    {
        "topic_key": "past_perfect", "error_category": "pp_before",
        "text": "Scholars discovered that the manuscript ___ been altered by a scribe centuries after its original composition.",
        "options": ["has", "had", "was", "were"],
        "correct_answer": "had",
    },
    {
        "topic_key": "past_perfect", "error_category": "pp_causality",
        "text": "She struggled to follow the advanced seminar because she ___ read the required preparatory material.",
        "options": ["didn't", "hadn't", "hasn't", "wasn't"],
        "correct_answer": "hadn't",
    },
    {
        "topic_key": "past_perfect", "error_category": "pp_sequence",
        "text": "The expedition team ___ never encountered conditions as extreme as those they faced in the Arctic.",
        "options": ["has", "have", "had", "was"],
        "correct_answer": "had",
    },

    {
        "topic_key": "present_perfect_cont", "error_category": "ppc_duration",
        "text": "The research team ___ the long-term effects of urban pollution on respiratory health for the past decade.",
        "options": ["has investigated", "has been investigating", "is investigating", "had been investigating"],
        "correct_answer": "has been investigating",
    },
    {
        "topic_key": "present_perfect_cont", "error_category": "ppc_ongoing_process",
        "text": "Negotiators ___ for six consecutive days in an effort to reach a diplomatic resolution.",
        "options": ["have met", "have been meeting", "met", "are meeting"],
        "correct_answer": "have been meeting",
    },
    {
        "topic_key": "present_perfect_cont", "error_category": "ppc_visible_result",
        "text": "She looks exhausted — she ___ non-stop since the international conference began three days ago.",
        "options": ["has worked", "has been working", "worked", "is working"],
        "correct_answer": "has been working",
    },
    {
        "topic_key": "present_perfect_cont", "error_category": "ppc_since_for",
        "text": "How long ___ they ___ this controversial methodology in their longitudinal study?",
        "options": ["have / been using", "did / use", "has / been using", "had / been using"],
        "correct_answer": "have / been using",
    },
]

GROUPS = [{"name": "Группа 101"}, {"name": "Группа 102"}, {"name": "Группа 103"}]

STUDENTS = [
    {"name": "Амина Сейткали",  "group_idx": 0, "streak_days": 12},
    {"name": "Диана Жакупова",  "group_idx": 0, "streak_days": 7},
    {"name": "Артём Волков",    "group_idx": 0, "streak_days": 5},
    {"name": "Камила Нурова",   "group_idx": 0, "streak_days": 9},
    {"name": "Максим Ли",       "group_idx": 0, "streak_days": 3},
    {"name": "Ерлан Беков",     "group_idx": 1, "streak_days": 2},
    {"name": "Света Попова",    "group_idx": 1, "streak_days": 4},
    {"name": "Нурлан Асанов",   "group_idx": 1, "streak_days": 1},
    {"name": "Алина Курманова", "group_idx": 1, "streak_days": 6},
    {"name": "Тимур Садыков",   "group_idx": 1, "streak_days": 0},
    {"name": "Руслан Омаров",   "group_idx": 2, "streak_days": 0},
    {"name": "Жанна Ахметова",  "group_idx": 2, "streak_days": 1},
    {"name": "Дархан Сатов",    "group_idx": 2, "streak_days": 0},
    {"name": "Айгерим Малик",   "group_idx": 2, "streak_days": 2},
    {"name": "Сырым Джаксов",   "group_idx": 2, "streak_days": 0},
]

GROUP_ACCURACY = [
    {1: (0.85, 0.98), 2: (0.75, 0.92), 3: (0.65, 0.85), 4: (0.55, 0.75)},
    {1: (0.65, 0.80), 2: (0.55, 0.72), 3: (0.45, 0.65), 4: (0.35, 0.55)},
    {1: (0.40, 0.60), 2: (0.30, 0.50), 3: (0.20, 0.42), 4: (0.15, 0.35)},
]


def seed_knowledge_graph(session: Session) -> None:
    if session.exec(select(Group)).first():
        return

    rng = random.Random(42)

    groups = []
    for g in GROUPS:
        grp = Group(**g)
        session.add(grp)
        groups.append(grp)
    session.commit()
    for g in groups:
        session.refresh(g)

    students = []
    base_date = datetime(2026, 5, 18)
    for s_data in STUDENTS:
        s = Student(
            name=s_data["name"],
            group_id=groups[s_data["group_idx"]].id,
            streak_days=s_data["streak_days"],
            last_active=base_date - timedelta(days=rng.randint(0, 2)),
        )
        session.add(s)
        students.append(s)
    session.commit()
    for s in students:
        session.refresh(s)

    topic_map: dict[str, TopicNode] = {}
    for t in TOPIC_NODES:
        node = TopicNode(**t)
        session.add(node)
    session.commit()
    for t in TOPIC_NODES:
        node = session.exec(select(TopicNode).where(TopicNode.key == t["key"])).one()
        topic_map[t["key"]] = node

    questions_by_topic: dict[str, list[Question]] = {}
    for q_data in QUESTIONS:
        q = Question(
            topic_node_id=topic_map[q_data["topic_key"]].id,
            text=q_data["text"],
            options=q_data["options"],
            correct_answer=q_data["correct_answer"],
            error_category=q_data["error_category"],
        )
        session.add(q)
        questions_by_topic.setdefault(q_data["topic_key"], []).append(q)
    session.commit()
    for key in questions_by_topic:
        refreshed = [session.exec(select(Question).where(Question.id == q.id)).one()
                     for q in questions_by_topic[key]]
        questions_by_topic[key] = refreshed

    week_start = datetime(2026, 4, 22)
    for s_idx, student in enumerate(students):
        group_idx = STUDENTS[s_idx]["group_idx"]
        acc_ranges = GROUP_ACCURACY[group_idx]
        for week in range(1, 5):
            week_date = week_start + timedelta(weeks=week - 1)
            topics_this_week = rng.sample(list(topic_map.keys()), k=min(7, len(topic_map)))
            for topic_key in topics_this_week:
                topic_node = topic_map[topic_key]
                lo, hi = acc_ranges[topic_node.difficulty]
                topic_acc = rng.uniform(lo, hi)
                qs = questions_by_topic.get(topic_key, [])
                if not qs:
                    continue
                for _ in range(rng.randint(2, 3)):
                    q = rng.choice(qs)
                    is_correct = rng.random() < topic_acc
                    if is_correct:
                        student_answer = q.correct_answer
                    else:
                        wrong = [o for o in q.options if o != q.correct_answer]
                        student_answer = rng.choice(wrong) if wrong else "???"
                    log = AnswerLog(
                        student_id=student.id,
                        question_id=q.id,
                        topic_node_id=topic_node.id,
                        student_answer=student_answer,
                        is_correct=is_correct,
                        answered_at=week_date + timedelta(days=rng.randint(0, 6),
                                                          hours=rng.randint(8, 20)),
                        week_number=week,
                    )
                    session.add(log)

    session.commit()
