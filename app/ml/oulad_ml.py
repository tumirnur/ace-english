from __future__ import annotations

import logging
from typing import Optional

import numpy as np
from sklearn.cluster import KMeans
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger(__name__)

RESULT_LABELS: dict[int, str] = {0: "Fail", 1: "Pass", 2: "Distinction"}
N_CLUSTERS = 4


def _extract_feature_vector(
    total_clicks: int,
    avg_weekly_clicks: float,
    assessment_avg_score: float,
    assessments_submitted: int,
    active_weeks: int,
    forum_clicks: int,
    resource_clicks: int,
    week_number: int,
) -> np.ndarray:
    active_ratio = active_weeks / max(week_number, 1)
    click_density = total_clicks / max(week_number, 1)
    return np.array([[
        total_clicks,
        avg_weekly_clicks,
        assessment_avg_score,
        assessments_submitted,
        active_ratio,
        forum_clicks,
        resource_clicks,
        click_density,
        week_number,
        week_number / 39.0,
    ]], dtype=float)


class OuladMLEngine:
    _instance: Optional[OuladMLEngine] = None

    def __init__(self) -> None:
        self._rf: Optional[RandomForestClassifier] = None
        self._kmeans: Optional[KMeans] = None
        self._scaler: Optional[StandardScaler] = None
        self._cluster_label_map: dict[int, str] = {}
        self._trained = False

    @classmethod
    def get(cls) -> OuladMLEngine:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def ensure_trained(self) -> None:
        if not self._trained:
            logger.info("Обучение OULAD ML-моделей на синтетических данных...")
            self._train()

    def _generate_training_data(self, n: int = 2000) -> tuple[np.ndarray, np.ndarray]:
        rng = np.random.default_rng(42)
        groups = [
            (0, int(n * 0.30),  50,  40, 36, 14, 0.42),
            (1, int(n * 0.50), 150,  60, 63, 10, 0.72),
            (2, int(n * 0.20), 290,  70, 82,  7, 0.91),
        ]
        X_rows, y_rows = [], []
        for label, cnt, cl_m, cl_s, sc_m, sc_s, act in groups:
            for _ in range(cnt):
                week = int(rng.integers(15, 39))
                total = max(0, int(rng.normal(cl_m * week / 30, cl_s * week / 30)))
                avg_w = total / max(week, 1)
                score = float(np.clip(rng.normal(sc_m, sc_s), 0, 100))
                n_asmts = int(rng.integers(1, 6))
                act_wks = max(1, int(rng.normal(act * week, 2)))
                forum = max(0, int(total * rng.uniform(0.05, 0.18)))
                resource = max(0, int(total * rng.uniform(0.35, 0.55)))
                X_rows.append(_extract_feature_vector(
                    total, avg_w, score, n_asmts, act_wks, forum, resource, week
                )[0])
                y_rows.append(label)
        return np.array(X_rows), np.array(y_rows)

    def _assign_cluster_labels(self, X: np.ndarray) -> None:
        assert self._scaler and self._kmeans
        labels = self._kmeans.predict(self._scaler.transform(X))
        stats = {}
        for c in range(N_CLUSTERS):
            mask = labels == c
            if mask.sum() > 0:
                stats[c] = X[mask, 0].mean() + X[mask, 2].mean() * 2
        ordered = sorted(stats, key=stats.get)
        semantic = ["Группа риска", "Пассивные", "Активные", "Отличники"]
        self._cluster_label_map = {
            ordered[i]: semantic[i] for i in range(min(len(ordered), len(semantic)))
        }

    def _train(self) -> None:
        X, y = self._generate_training_data()

        self._scaler = StandardScaler()
        X_scaled = self._scaler.fit_transform(X)

        self._rf = RandomForestClassifier(
            n_estimators=150, max_depth=12, min_samples_leaf=5,
            random_state=42, class_weight="balanced",
        )
        self._rf.fit(X, y)

        self._kmeans = KMeans(n_clusters=N_CLUSTERS, random_state=42, n_init=10)
        self._kmeans.fit(X_scaled)

        self._assign_cluster_labels(X)
        self._trained = True
        logger.info("OULAD ML-модели успешно обучены.")

    def predict(
        self,
        total_clicks: int,
        avg_weekly_clicks: float,
        assessment_avg_score: float,
        assessments_submitted: int,
        active_weeks: int,
        forum_clicks: int,
        resource_clicks: int,
        week_number: int,
    ) -> dict:
        self.ensure_trained()
        assert self._rf and self._kmeans and self._scaler

        X = _extract_feature_vector(
            total_clicks, avg_weekly_clicks, assessment_avg_score,
            assessments_submitted, active_weeks, forum_clicks,
            resource_clicks, week_number,
        )

        probas = self._rf.predict_proba(X)[0]
        classes = self._rf.classes_
        proba_dict = {RESULT_LABELS[int(c)]: round(float(p), 3) for c, p in zip(classes, probas)}
        predicted = int(self._rf.predict(X)[0])

        cluster_raw = int(self._kmeans.predict(self._scaler.transform(X))[0])
        cluster_label = self._cluster_label_map.get(cluster_raw, f"Кластер {cluster_raw}")

        return {
            "prediction": RESULT_LABELS[predicted],
            "probabilities": proba_dict,
            "pass_probability": round(
                proba_dict.get("Pass", 0.0) + proba_dict.get("Distinction", 0.0), 3
            ),
            "cluster_id": cluster_raw,
            "cluster_label": cluster_label,
        }
