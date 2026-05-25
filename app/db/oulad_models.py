from typing import Optional

from sqlmodel import Field, SQLModel


class OuladStudent(SQLModel, table=True):
    __tablename__ = "oulad_student"

    id: Optional[int] = Field(default=None, primary_key=True)
    code_module: str = Field(default="BBB", index=True)
    code_presentation: str = Field(default="2014J", index=True)
    gender: str = Field(default="M")
    region: str = Field(default="East Anglian Region")
    highest_education: str = Field(default="HE Qualification")
    age_band: str = Field(default="35-55")
    num_prev_attempts: int = Field(default=0)
    studied_credits: int = Field(default=60)
    final_result: str = Field(default="Pass")


class WeeklyActivity(SQLModel, table=True):
    __tablename__ = "weekly_activity"

    id: Optional[int] = Field(default=None, primary_key=True)
    student_id: int = Field(index=True)
    week: int = Field(index=True)
    total_clicks: int = Field(default=0)
    forum_clicks: int = Field(default=0)
    resource_clicks: int = Field(default=0)
    quiz_clicks: int = Field(default=0)
    homepage_clicks: int = Field(default=0)


class AssessmentScore(SQLModel, table=True):
    __tablename__ = "assessment_score"

    id: Optional[int] = Field(default=None, primary_key=True)
    student_id: int = Field(index=True)
    week_submitted: int = Field(default=1)
    assessment_type: str = Field(default="TMA")
    score: float = Field(default=0.0)
    is_submitted: bool = Field(default=True)
