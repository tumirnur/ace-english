from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TestQuestion:
    question: str
    options: list[str]
    correct_index: int
    error_type: str


@dataclass
class KnowledgeNode:
    id: str
    title: str
    description: str
    prerequisites: list[str]
    remediation_map: dict[str, str]
    questions: list[TestQuestion] = field(default_factory=list)
    x: int = 0
    y: int = 0


KNOWLEDGE_GRAPH: dict[str, KnowledgeNode] = {
    "variables": KnowledgeNode(
        id="variables",
        title="Переменные",
        description="Присваивание значений, базовые типы данных: int, str, float, bool.",
        prerequisites=[],
        remediation_map={},
        x=90, y=190,
        questions=[
            TestQuestion(
                question="Какой результат у выражения: x = 5; y = 3; print(x + y)?",
                options=["53", "8", "5+3", "Ошибка"],
                correct_index=1,
                error_type="arithmetic",
            ),
            TestQuestion(
                question="Какой тип данных у значения '42' (в кавычках)?",
                options=["int", "float", "str", "bool"],
                correct_index=2,
                error_type="type_confusion",
            ),
        ],
    ),

    "conditions": KnowledgeNode(
        id="conditions",
        title="Условия (if/else)",
        description="Ветвления: if, elif, else. Булевы выражения и операторы сравнения.",
        prerequisites=["variables"],
        remediation_map={
            "logic_error": "variables",
            "boolean_error": "variables",
        },
        x=270, y=80,
        questions=[
            TestQuestion(
                question="Что выведет: x=10; print('big' if x > 5 else 'small')?",
                options=["big", "small", "10", "True"],
                correct_index=0,
                error_type="logic_error",
            ),
            TestQuestion(
                question="Какое условие истинно при x = 3?",
                options=["x > 5", "x == 4", "x < 10", "x != 3"],
                correct_index=2,
                error_type="boolean_error",
            ),
        ],
    ),

    "lists": KnowledgeNode(
        id="lists",
        title="Списки",
        description="Создание списков, методы append/remove, итерация, функция len().",
        prerequisites=["variables"],
        remediation_map={
            "index_error": "list_indexing",
            "type_error": "variables",
        },
        x=270, y=300,
        questions=[
            TestQuestion(
                question="Что выведет: a = [1, 2, 3]; print(len(a))?",
                options=["1", "2", "3", "6"],
                correct_index=2,
                error_type="len_confusion",
            ),
            TestQuestion(
                question="Как добавить элемент 4 в список a = [1, 2, 3]?",
                options=["a.add(4)", "a.append(4)", "a.insert(4)", "a + 4"],
                correct_index=1,
                error_type="method_error",
            ),
        ],
    ),

    "list_indexing": KnowledgeNode(
        id="list_indexing",
        title="Индексация",
        description="Обращение по индексу (a[i]), срезы (a[1:3]), отрицательные индексы.",
        prerequisites=["lists"],
        remediation_map={
            "index_error": "lists",
            "negative_index": "lists",
        },
        x=460, y=300,
        questions=[
            TestQuestion(
                question="Что выведет: a = [10, 20, 30]; print(a[1])?",
                options=["10", "20", "30", "IndexError"],
                correct_index=1,
                error_type="index_error",
            ),
            TestQuestion(
                question="Что выведет: a = [1, 2, 3]; print(a[-1])?",
                options=["1", "-1", "3", "IndexError"],
                correct_index=2,
                error_type="negative_index",
            ),
        ],
    ),

    "for_loops": KnowledgeNode(
        id="for_loops",
        title="Цикл For",
        description="Перебор элементов списка, функция range(), накопление результата.",
        prerequisites=["conditions", "list_indexing"],
        remediation_map={
            "index_error": "list_indexing",
            "range_error": "list_indexing",
            "logic_error": "conditions",
        },
        x=570, y=155,
        questions=[
            TestQuestion(
                question="Сколько итераций у: for i in range(3): print(i)?",
                options=["2", "3", "4", "0"],
                correct_index=1,
                error_type="range_error",
            ),
            TestQuestion(
                question="Что выведет: a=[1,2,3]; s=0\nfor x in a: s+=x\nprint(s)?",
                options=["6", "3", "1", "123"],
                correct_index=0,
                error_type="logic_error",
            ),
        ],
    ),
}

TRAVERSAL_ORDER = ["variables", "lists", "list_indexing", "conditions", "for_loops"]

EDGES: list[tuple[str, str]] = [
    ("variables", "conditions"),
    ("variables", "lists"),
    ("lists", "list_indexing"),
    ("list_indexing", "for_loops"),
    ("conditions", "for_loops"),
]


def get_remediation_node(node_id: str, error_type: str) -> Optional[str]:
    node = KNOWLEDGE_GRAPH.get(node_id)
    if not node:
        return None
    return node.remediation_map.get(error_type)


def get_graph_for_frontend() -> dict:
    nodes = [
        {
            "id": n.id,
            "title": n.title,
            "description": n.description,
            "prerequisites": n.prerequisites,
            "x": n.x,
            "y": n.y,
            "question_count": len(n.questions),
        }
        for n in KNOWLEDGE_GRAPH.values()
    ]
    edges = [{"from": f, "to": t} for f, t in EDGES]
    return {"nodes": nodes, "edges": edges, "order": TRAVERSAL_ORDER}


def get_next_question(node_id: str, question_index: int) -> Optional[dict]:
    node = KNOWLEDGE_GRAPH.get(node_id)
    if not node or question_index >= len(node.questions):
        return None
    q = node.questions[question_index]
    return {
        "node_id": node_id,
        "question_index": question_index,
        "question": q.question,
        "options": q.options,
        "total": len(node.questions),
    }


def check_answer(node_id: str, question_index: int, selected_index: int) -> dict:
    node = KNOWLEDGE_GRAPH.get(node_id)
    if not node or question_index >= len(node.questions):
        return {"is_correct": False, "error": "Узел или вопрос не найден"}

    q = node.questions[question_index]
    is_correct = selected_index == q.correct_index

    return {
        "is_correct": is_correct,
        "correct_index": q.correct_index,
        "error_type": None if is_correct else q.error_type,
        "remediation_node": None if is_correct else get_remediation_node(node_id, q.error_type),
    }
