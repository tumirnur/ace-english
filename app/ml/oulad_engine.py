from __future__ import annotations

import logging
import threading
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger(__name__)

STUDENT_KEYS = ["code_module", "code_presentation", "id_student"]
FEATURE_COLS = ["weight_score", "total_clicks", "clicks_forum", "clicks_pdf_like"]
RF_CLASSES = ["Fail", "Pass", "Distinction"]

ACTIVITY_TYPE_RU = {
    "forumng": "Форум", "resource": "Файлы/материалы", "oucontent": "Страница урока",
    "quiz": "Тест", "subpage": "Подраздел курса", "url": "Внешняя ссылка",
    "questionnaire": "Опрос", "page": "Страница курса", "glossary": "Глоссарий",
    "ouwiki": "Вики курса", "virtualclassroom": "Онлайн-занятие",
    "htmlactivity": "Интерактивное задание", "lesson": "Урок",
    "oucollaborate": "Совместная работа", "repeatactivity": "Повторяемое задание",
    "externalquiz": "Внешний тест", "homepage": "Главная страница курса",
}


def _build_preprocessor() -> ColumnTransformer:
    return ColumnTransformer([
        ("num", Pipeline([("imp", SimpleImputer(strategy="median")), ("sc", StandardScaler())]), FEATURE_COLS)
    ], remainder="drop")


class OuladEngine:
    def __init__(self) -> None:
        self._ready = False
        self._error: str = ""
        self._feature_df: pd.DataFrame | None = None
        self._weekly_df: pd.DataFrame | None = None
        self._vle_activity_df: pd.DataFrame | None = None
        self._kmeans: KMeans | None = None
        self._rf: RandomForestClassifier | None = None
        self._preprocess: ColumnTransformer | None = None
        self._cluster_names: dict[int, str] = {}
        self._lock = threading.Lock()

    @property
    def ready(self) -> bool:
        return self._ready

    @property
    def error(self) -> str:
        return self._error

    def load_and_train(self, data_dir: Path) -> None:
        data_dir = Path(data_dir)
        required = ["studentAssessment.csv", "assessments.csv",
                    "studentVle.csv", "vle.csv", "studentInfo.csv"]
        missing = [f for f in required if not (data_dir / f).exists()]
        if missing:
            self._error = f"Не найдены файлы OULAD: {missing}"
            logger.warning(self._error)
            return

        try:
            logger.info("OULAD: загружаем CSV…")
            scores = self._compute_weighted_scores(
                pd.read_csv(data_dir / "studentAssessment.csv"),
                pd.read_csv(data_dir / "assessments.csv"),
            )
            vle = pd.read_csv(data_dir / "vle.csv")
            clicks, activity_df, weekly_df = self._aggregate_vle(
                data_dir / "studentVle.csv", vle
            )
            info = self._load_info(pd.read_csv(data_dir / "studentInfo.csv"))

            feat = info.merge(scores, on=STUDENT_KEYS, how="left")
            feat = feat.merge(clicks, on=STUDENT_KEYS, how="left")
            for c in ["total_clicks", "clicks_forum", "clicks_pdf_like"]:
                feat[c] = feat[c].fillna(0)
            feat["weight_score"] = pd.to_numeric(feat["weight_score"], errors="coerce")

            self._feature_df = feat
            self._weekly_df = weekly_df
            self._vle_activity_df = activity_df
            logger.info("OULAD: загружено %d студентов, обучаем модели…", len(feat))

            self._train(feat)
            self._ready = True
            logger.info("OULAD: модели готовы.")
        except Exception as exc:
            self._error = str(exc)
            logger.exception("OULAD: ошибка при загрузке/обучении")

    def _compute_weighted_scores(self, sa: pd.DataFrame, asm: pd.DataFrame) -> pd.DataFrame:
        sa["score"] = pd.to_numeric(sa["score"], errors="coerce")
        asm["weight"] = pd.to_numeric(asm["weight"], errors="coerce").fillna(0)
        m = sa.merge(asm[["id_assessment", "code_module", "code_presentation", "weight"]],
                     on="id_assessment", how="left")
        m = m.dropna(subset=["score", "weight"])
        m = m[m["weight"] > 0]
        m["weighted"] = m["score"] * m["weight"]
        g = m.groupby(STUDENT_KEYS, as_index=False).agg(
            ws=("weighted", "sum"), wsum=("weight", "sum"))
        g["weight_score"] = np.where(g["wsum"] > 0, g["ws"] / g["wsum"], np.nan)
        return g[STUDENT_KEYS + ["weight_score"]]

    def _aggregate_vle(self, vle_path: Path, vle: pd.DataFrame):
        vle_small = vle[["id_site", "code_module", "code_presentation", "activity_type"]].drop_duplicates()
        totals, weekly_parts, activity_parts = [], [], []

        for chunk in pd.read_csv(vle_path, chunksize=500_000,
                                  dtype={"code_module": str, "code_presentation": str}):
            chunk["id_site"] = pd.to_numeric(chunk["id_site"], errors="coerce")
            chunk["sum_click"] = pd.to_numeric(chunk["sum_click"], errors="coerce").fillna(0)
            chunk["id_student"] = pd.to_numeric(chunk["id_student"], errors="coerce")
            chunk = chunk.dropna(subset=["id_student"])
            chunk["id_student"] = chunk["id_student"].astype(int)

            m = chunk.merge(vle_small, on=["id_site", "code_module", "code_presentation"], how="left")
            m["activity_type"] = m["activity_type"].fillna("unknown")

            totals.append(m.groupby(STUDENT_KEYS + ["activity_type"], as_index=False)["sum_click"].sum())

            days = pd.to_numeric(chunk["date"], errors="coerce").fillna(0)
            chunk["week_index"] = (days // 7).astype("int64")
            weekly_parts.append(
                chunk.groupby(STUDENT_KEYS + ["week_index"], as_index=False)["sum_click"].sum()
            )

            activity_parts.append(
                m.groupby(STUDENT_KEYS + ["activity_type"], as_index=False)["sum_click"].sum()
            )

        if not totals:
            empty = pd.DataFrame(columns=STUDENT_KEYS + ["total_clicks", "clicks_forum", "clicks_pdf_like"])
            return empty, pd.DataFrame(), pd.DataFrame()

        summed = pd.concat(totals).groupby(STUDENT_KEYS + ["activity_type"], as_index=False)["sum_click"].sum()
        pivot = summed.pivot_table(index=STUDENT_KEYS, columns="activity_type",
                                    values="sum_click", aggfunc="sum", fill_value=0).reset_index()
        act_cols = [c for c in pivot.columns if c not in STUDENT_KEYS]
        pivot["total_clicks"] = pivot[act_cols].sum(axis=1)
        pivot["clicks_forum"] = pivot.get("forumng", pd.Series(0, index=pivot.index))
        pdf = pd.Series(0.0, index=pivot.index)
        for c in ["resource", "oucontent"]:
            if c in pivot.columns:
                pdf += pivot[c].astype(float)
        pivot["clicks_pdf_like"] = pdf

        weekly = pd.concat(weekly_parts).groupby(
            STUDENT_KEYS + ["week_index"], as_index=False)["sum_click"].sum()
        activity_agg = pd.concat(activity_parts).groupby(
            STUDENT_KEYS + ["activity_type"], as_index=False)["sum_click"].sum()

        return pivot[STUDENT_KEYS + ["total_clicks", "clicks_forum", "clicks_pdf_like"]], \
               activity_agg, weekly

    def _load_info(self, info: pd.DataFrame) -> pd.DataFrame:
        cols = STUDENT_KEYS + ["final_result", "gender", "age_band", "highest_education",
                               "studied_credits", "num_of_prev_attempts"]
        cols = [c for c in cols if c in info.columns]
        out = info[cols].copy().dropna(subset=["final_result"])
        for c in ["code_module", "code_presentation", "final_result"]:
            if c in out.columns:
                out[c] = out[c].astype(str).str.strip()
        out["id_student"] = pd.to_numeric(out["id_student"], errors="coerce").dropna().astype(int)
        return out.drop_duplicates(subset=STUDENT_KEYS, keep="last")

    def _train(self, df: pd.DataFrame) -> None:
        work = df[df["final_result"].isin(RF_CLASSES)].copy().reset_index(drop=True)
        X = work[FEATURE_COLS].copy()
        self._preprocess = _build_preprocessor()
        X_t = self._preprocess.fit_transform(X)

        self._kmeans = KMeans(n_clusters=3, random_state=42, n_init=10)
        clusters = self._kmeans.fit_predict(X_t)
        work["cluster"] = clusters
        stats = work.groupby("cluster").agg(mc=("total_clicks", "mean"), ms=("weight_score", "mean"))
        active = int(stats["mc"].idxmax())
        rest = [i for i in stats.index if i != active]
        rest_stats = stats.loc[rest]
        results = int(rest_stats["ms"].idxmax())
        risk = [i for i in rest if i != results][0]
        self._cluster_names = {active: "Активные", results: "Результативные", risk: "Группа риска"}

        y = work["final_result"]
        self._rf = RandomForestClassifier(n_estimators=200, max_depth=12,
                                           random_state=42, class_weight="balanced_subsample")
        self._rf.fit(X_t, y)

    def lookup_student(self, id_student: int,
                       code_module: str | None = None,
                       code_presentation: str | None = None) -> dict:
        if not self._ready or self._feature_df is None:
            return {"error": "OULAD не загружен"}

        df = self._feature_df
        mask = df["id_student"] == id_student
        if code_module:
            mask &= df["code_module"].str.upper() == code_module.upper()
        if code_presentation:
            mask &= df["code_presentation"].str.upper() == code_presentation.upper()

        rows = df[mask]
        if rows.empty:
            return {"error": f"Студент {id_student} не найден в данных OULAD"}
        if len(rows) > 1 and not (code_module and code_presentation):
            courses = rows[["code_module", "code_presentation"]].drop_duplicates().to_dict("records")
            return {"multiple": True, "courses": courses, "id_student": id_student}

        row = rows.iloc[0]
        prediction = self._predict_row(row)
        weekly = self._get_weekly(id_student, row["code_module"], row["code_presentation"])
        activity = self._get_activity(id_student, row["code_module"], row["code_presentation"])

        return {
            "id_student": int(id_student),
            "code_module": str(row["code_module"]),
            "code_presentation": str(row["code_presentation"]),
            "final_result_known": str(row.get("final_result", "?")),
            "gender": str(row.get("gender", "?")),
            "age_band": str(row.get("age_band", "?")),
            "studied_credits": int(row.get("studied_credits", 0)),
            "num_of_prev_attempts": int(row.get("num_of_prev_attempts", 0)),
            "total_clicks": int(row.get("total_clicks", 0)),
            "clicks_forum": int(row.get("clicks_forum", 0)),
            "clicks_pdf_like": int(row.get("clicks_pdf_like", 0)),
            "weight_score": float(row["weight_score"]) if pd.notna(row.get("weight_score")) else None,
            **prediction,
            "weekly_clicks": weekly,
            "activity_breakdown": activity,
        }

    def _predict_row(self, row: pd.Series) -> dict:
        if self._rf is None or self._kmeans is None or self._preprocess is None:
            return {}
        X = pd.DataFrame([{c: row.get(c, np.nan) for c in FEATURE_COLS}])
        X_t = self._preprocess.transform(X)
        proba = dict(zip(self._rf.classes_, self._rf.predict_proba(X_t)[0]))
        cluster_id = int(self._kmeans.predict(X_t)[0])
        success_prob = float(proba.get("Pass", 0) + proba.get("Distinction", 0))
        return {
            "predicted_class": max(proba, key=proba.get),
            "class_probabilities": {k: round(float(v), 4) for k, v in proba.items()},
            "success_probability": round(success_prob, 4),
            "learning_style": self._cluster_names.get(cluster_id, str(cluster_id)),
            "cluster_id": cluster_id,
        }

    def _get_weekly(self, sid: int, module: str, pres: str) -> list[dict]:
        if self._weekly_df is None:
            return []
        df = self._weekly_df
        mask = (df["id_student"] == sid) & (df["code_module"].str.upper() == module.upper()) & \
               (df["code_presentation"].str.upper() == pres.upper())
        rows = df[mask].sort_values("week_index")
        return [{"week": int(r.week_index), "clicks": int(r.sum_click)} for _, r in rows.iterrows()]

    def _get_activity(self, sid: int, module: str, pres: str) -> list[dict]:
        if self._vle_activity_df is None:
            return []
        df = self._vle_activity_df
        mask = (df["id_student"] == sid) & (df["code_module"].str.upper() == module.upper()) & \
               (df["code_presentation"].str.upper() == pres.upper())
        rows = df[mask].sort_values("sum_click", ascending=False)
        return [
            {"activity_type": str(r.activity_type),
             "activity_ru": ACTIVITY_TYPE_RU.get(str(r.activity_type), str(r.activity_type)),
             "clicks": int(r.sum_click)}
            for _, r in rows.iterrows()
        ]

    def cohort_stats(self, code_module: str | None = None,
                     code_presentation: str | None = None) -> dict:
        if not self._ready or self._feature_df is None:
            return {}
        df = self._feature_df.copy()
        if code_module:
            df = df[df["code_module"].str.upper() == code_module.upper()]
        if code_presentation:
            df = df[df["code_presentation"].str.upper() == code_presentation.upper()]
        if df.empty:
            return {}
        result_counts = df["final_result"].value_counts(normalize=True).to_dict()
        return {
            "total": len(df),
            "result_distribution": {k: round(float(v), 3) for k, v in result_counts.items()},
            "avg_clicks": round(float(df["total_clicks"].mean()), 1),
            "avg_score": round(float(df["weight_score"].mean()), 1) if df["weight_score"].notna().any() else None,
        }


    def sample_students(self, n: int = 20) -> list[dict]:
        if not self._ready or self._feature_df is None:
            return []
        df = self._feature_df.dropna(subset=["weight_score"]).copy()
        parts = []
        per_class = n // 3
        for cls in ["Pass", "Distinction", "Fail"]:
            sub = df[df["final_result"] == cls]
            take = per_class if cls != "Fail" else n - 2 * per_class
            if len(sub) >= take:
                parts.append(sub.sample(take, random_state=42))
            elif len(sub) > 0:
                parts.append(sub)
        if not parts:
            return []
        sample = pd.concat(parts).reset_index(drop=True)
        sample_sorted = sample.sort_values("weight_score", ascending=False).reset_index(drop=True)
        result = []
        total = len(sample_sorted)
        for i, (_, row) in enumerate(sample_sorted.iterrows()):
            pred = self._predict_row(row)
            result.append({
                "id_student": int(row["id_student"]),
                "code_module": str(row["code_module"]),
                "code_presentation": str(row["code_presentation"]),
                "final_result": str(row.get("final_result", "?")),
                "weight_score": round(float(row["weight_score"]), 1),
                "total_clicks": int(row.get("total_clicks", 0)),
                "gender": str(row.get("gender", "?")),
                "age_band": str(row.get("age_band", "?")),
                "studied_credits": int(row.get("studied_credits", 0)),
                "num_of_prev_attempts": int(row.get("num_of_prev_attempts", 0)),
                "predicted_class": pred.get("predicted_class"),
                "learning_style": pred.get("learning_style"),
                "success_probability": pred.get("success_probability"),
                "rank": i + 1,
                "sample_size": total,
            })
        return result


oulad_engine = OuladEngine()
