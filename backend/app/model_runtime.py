from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping


def _parse_base_score(value: object) -> float:
    text = str(value).strip().strip("[]")
    return float(text)


class XGBoostJsonRegressor:
    """Minimal XGBoost gbtree inference for a single-output regression model.

    Loading the model's portable JSON avoids shipping XGBoost, NumPy and SciPy in
    the Vercel function while preserving the trained tree thresholds and leaves.
    """

    def __init__(self, model_path: Path) -> None:
        with model_path.open(encoding="utf-8") as model_file:
            document = json.load(model_file)

        learner = document["learner"]
        booster = learner["gradient_booster"]
        if booster.get("name") != "gbtree":
            raise ValueError("Only XGBoost gbtree models are supported")
        if learner["objective"].get("name") != "reg:squarederror":
            raise ValueError("Only reg:squarederror models are supported")

        self.feature_names: list[str] = learner["feature_names"]
        self.base_score = _parse_base_score(
            learner["learner_model_param"]["base_score"]
        )
        self.trees: list[dict[str, object]] = booster["model"]["trees"]

    def predict(self, features: Mapping[str, float]) -> float:
        values = [float(features[name]) for name in self.feature_names]
        prediction = self.base_score

        for tree in self.trees:
            left_children = tree["left_children"]
            right_children = tree["right_children"]
            split_indices = tree["split_indices"]
            split_conditions = tree["split_conditions"]
            default_left = tree["default_left"]

            node = 0
            while left_children[node] != -1:
                value = values[split_indices[node]]
                if value != value:  # NaN follows the model's stored default path.
                    node = left_children[node] if default_left[node] else right_children[node]
                elif value < split_conditions[node]:
                    node = left_children[node]
                else:
                    node = right_children[node]
            prediction += split_conditions[node]

        return prediction
