"""
Feedback learning. The user's Notion Status choices (Applied/Interested =
positive, Skip/Rejected = negative) are distilled into data/feedback.json by
feedback_sync.py, and replayed here as a prompt bias for future scoring.
"""
import json
from pathlib import Path

FEEDBACK_PATH = Path(__file__).resolve().parent.parent / "data" / "feedback.json"


def load_feedback() -> dict:
    if FEEDBACK_PATH.exists():
        try:
            data = json.loads(FEEDBACK_PATH.read_text())
            return {"positive": data.get("positive", []), "negative": data.get("negative", [])}
        except (json.JSONDecodeError, OSError):
            pass
    return {"positive": [], "negative": []}


def save_feedback(fb: dict) -> None:
    FEEDBACK_PATH.parent.mkdir(parents=True, exist_ok=True)
    FEEDBACK_PATH.write_text(json.dumps(
        {"positive": fb.get("positive", []), "negative": fb.get("negative", [])}, indent=2
    ))


def build_preference_prompt(feedback: dict, max_examples: int = 15) -> str:
    """Turn feedback history into a bias section for the scoring prompt."""
    lines: list[str] = []
    if feedback.get("positive"):
        lines.append("# Listings the user LIKED (positive signal — score similar ones higher):")
        lines += [f"- {e}" for e in feedback["positive"][-max_examples:]]
    if feedback.get("negative"):
        lines.append("\n# Listings the user SKIPPED/REJECTED (negative signal — score similar ones lower):")
        lines += [f"- {e}" for e in feedback["negative"][-max_examples:]]
    if lines:
        lines.append("\nUse these patterns to bias scoring on the new listings above.")
    return "\n".join(lines)
