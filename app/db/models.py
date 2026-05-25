from datetime import datetime
from typing import List, Optional

from sqlalchemy import Column
from sqlalchemy.types import JSON
from sqlmodel import Field, Relationship, SQLModel


class Group(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(unique=True)

    students: List["Student"] = Relationship(back_populates="group")


class Student(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    group_id: int = Field(foreign_key="group.id")
    streak_days: int = Field(default=0)
    last_active: Optional[datetime] = Field(default=None)
    password: str = Field(default="")

    group: Optional[Group] = Relationship(back_populates="students")
    answer_logs: List["AnswerLog"] = Relationship(back_populates="student")


class TopicNode(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    key: str = Field(unique=True, index=True)
    title: str
    description: str
    theory: str = Field(default="")
    difficulty: int = Field(ge=1, le=5)
    prerequisite_keys: List[str] = Field(default_factory=list, sa_column=Column(JSON))
    pos_x: float = Field(default=0)
    pos_y: float = Field(default=0)

    questions: List["Question"] = Relationship(back_populates="topic_node")


class Question(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    topic_node_id: int = Field(foreign_key="topicnode.id", index=True)
    text: str
    options: List[str] = Field(default_factory=list, sa_column=Column(JSON))
    correct_answer: str
    error_category: str

    topic_node: Optional[TopicNode] = Relationship(back_populates="questions")
    answer_logs: List["AnswerLog"] = Relationship(back_populates="question")


class AnswerLog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    student_id: int = Field(foreign_key="student.id", index=True)
    question_id: int = Field(foreign_key="question.id")
    topic_node_id: int = Field(foreign_key="topicnode.id")
    student_answer: str
    is_correct: bool
    ai_problem: Optional[str] = Field(default=None)
    redirected_to_key: Optional[str] = Field(default=None)
    answered_at: datetime = Field(default_factory=datetime.utcnow)
    week_number: int = Field(default=1)

    student: Optional[Student] = Relationship(back_populates="answer_logs")
    question: Optional[Question] = Relationship(back_populates="answer_logs")
