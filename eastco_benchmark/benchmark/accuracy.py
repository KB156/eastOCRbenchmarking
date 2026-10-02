from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_ground_truth(path: Path) -> dict[str, dict[str, Any]]:
    records = {}
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            record = json.loads(line)
            records[record["document_id"]] = record["fields"]
    return records


def score_fields(predicted: dict[str, Any], expected: dict[str, Any]) -> dict[str, Any]:
    field_scores = {}
    comparable_fields = [key for key in expected.keys() if key != "line_items"]
    matches = 0
    for key in comparable_fields:
        expected_value = expected.get(key)
        predicted_value = predicted.get(key)
        match = normalize(predicted_value) == normalize(expected_value)
        field_scores[key] = match
        matches += 1 if match else 0

    expected_items = expected.get("line_items", [])
    predicted_items = predicted.get("line_items", [])
    line_item_match = len(expected_items) == len(predicted_items)
    if line_item_match:
        for expected_item, predicted_item in zip(expected_items, predicted_items):
            if normalize(expected_item.get("description")) != normalize(predicted_item.get("description")):
                line_item_match = False
            if float(expected_item.get("amount", 0)) != float(predicted_item.get("amount", 0)):
                line_item_match = False
    field_scores["line_items"] = line_item_match
    total_fields = len(comparable_fields) + 1
    accuracy = (matches + (1 if line_item_match else 0)) / total_fields if total_fields else 0.0
    return {"field_accuracy": round(accuracy, 4), "field_matches": field_scores}


def normalize(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value).strip().lower()
