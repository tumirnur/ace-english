import os
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.db.database import engine, get_session, init_db
from app.db.models import Group, Student, TopicNode, Question, AnswerLog
from app.db.seed import seed_knowledge_graph
from app.ml.oulad_engine import oulad_engine
from sqlmodel import SQLModel, Session

_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
_DOCS_DIR = Path(__file__).resolve().parent.parent / "docs"
_OULAD_DIR = Path(os.environ.get("OULAD_DATA_DIR", "/Users/elina/Downloads/anonymisedData"))


@asynccontextmanager
async def lifespan(_: FastAPI):
    SQLModel.metadata.drop_all(engine)
    init_db()
    with Session(engine) as session:
        seed_knowledge_graph(session)
    if _OULAD_DIR.exists():
        t = threading.Thread(
            target=oulad_engine.load_and_train,
            args=(_OULAD_DIR,),
            daemon=True,
        )
        t.start()
    yield


app = FastAPI(
    title="English Tenses — Adaptive Learning",
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/docs",
)

app.include_router(router)

if _STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


@app.get("/", include_in_schema=False)
def home():
    spa = _STATIC_DIR / "index.html"
    if spa.exists():
        return FileResponse(str(spa))
    return {"error": "Frontend not found"}


@app.get("/техническая-документация", include_in_schema=False)
def download_docs():
    docx = _DOCS_DIR / "Техническая_документация.docx"
    if docx.exists():
        return FileResponse(
            str(docx),
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            filename="Техническая_документация.docx",
        )
    return {"error": "Документ не найден"}
