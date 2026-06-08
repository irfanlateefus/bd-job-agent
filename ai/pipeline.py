"""
Batch AI enrichment. Scores each listing 0-100 against the BD profile, with a
2-sentence summary and a "why it matches or doesn't" note. Always batches
(batch_size items per call) to stay inside the Gemini free tier.
"""
import json
from pathlib import Path

import yaml

from ai.client import generate

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"


def _config() -> dict:
    return yaml.safe_load(CONFIG_PATH.read_text()) if CONFIG_PATH.exists() else {}


def _coerce_score(value) -> int:
    """Clamp any model-emitted score to an int in [0, 100]; 0 on garbage."""
    try:
        return max(0, min(100, int(float(value))))
    except (TypeError, ValueError):
        return 0


def analyse_batch(items: list[dict], personas: list[dict], preference_prompt: str = "") -> list[dict]:
    """Return items enriched with persona / ai_score / ai_summary / ai_notes.

    Each listing is scored against the single best-fit persona — the model picks
    which persona (from `personas`) the role belongs to, then scores fit to it.
    `personas` is a list of {name, context} (see filters.load_personas()).
    """
    config = _config()
    ai_cfg = config.get("ai", {}) or {}
    model = ai_cfg.get("model", "gemini-2.0-flash-lite")
    rate_limit = float(ai_cfg.get("rate_limit_seconds", 7.0))
    min_score = int(ai_cfg.get("min_score", 0))
    batch_size = int(ai_cfg.get("batch_size", 5))
    persona_names = {p.get("name") for p in personas}

    batches = [items[i:i + batch_size] for i in range(0, len(items), batch_size)]
    print(f"  [AI] {len(items)} items -> {len(batches)} API calls (batch={batch_size}); "
          f"personas: {', '.join(sorted(n for n in persona_names if n))}")

    enriched: list[dict] = []
    for i, batch in enumerate(batches):
        print(f"  [AI] batch {i + 1}/{len(batches)}...")
        prompt = _build_prompt(batch, personas, preference_prompt)
        # Scale the output budget to the batch so verbose responses aren't truncated.
        max_tokens = min(8192, max(2048, 600 * len(batch)))
        result = generate(prompt, model=model, rate_limit=rate_limit, max_output_tokens=max_tokens)
        analyses = result.get("analyses", []) if isinstance(result, dict) else []
        if len(analyses) != len(batch):
            print(f"  [AI] WARNING: {len(analyses)} analyses for {len(batch)} items "
                  f"(batch {i + 1}) — unmatched items kept unscored")

        # Map analyses to items by the item_id we sent (robust to reorder/drop),
        # falling back to positional order when the model omits the id.
        by_id: dict = {}
        for idx, a in enumerate(analyses):
            if not isinstance(a, dict):
                continue
            key = a.get("item_id")
            by_id[idx if key is None else key] = a

        for j, item in enumerate(batch):
            ai = by_id.get(j)
            if not isinstance(ai, dict):
                # No analysis for this item. A configured floor means "don't
                # surface unknowns" either, so only keep unscored when min_score is 0.
                if not min_score:
                    enriched.append(item)
                continue
            score = _coerce_score(ai.get("score"))
            if min_score and score < min_score:
                continue
            persona = ai.get("persona", "")
            if persona not in persona_names:
                persona = ""  # ignore a hallucinated persona name
            enriched.append({
                **item,
                "persona": persona,
                "ai_score": score,
                "ai_summary": ai.get("summary", ""),
                "ai_notes": ai.get("notes", ""),
            })

    return enriched


def _build_prompt(batch: list[dict], personas: list[dict], preference_prompt: str) -> str:
    persona_blocks = "\n\n".join(
        f"### Persona: {p.get('name', '?')}\n{(p.get('context') or 'Not provided')[:1600]}"
        for p in personas
    )
    names = " | ".join(p.get("name", "?") for p in personas)
    items_text = "\n\n".join(
        f"Item {i}: " + json.dumps(
            {"item_id": i, **{k: v for k, v in item.items() if not k.startswith('_')}}
        )
        for i, item in enumerate(batch)
    )

    return f"""You are scoring job listings for a candidate pursuing multiple target personas.

# Candidate personas
{persona_blocks}

# Listings
{items_text}

{preference_prompt}

# Instructions
For EACH listing: choose the SINGLE best-fit persona (exactly one of: {names}), then score 0-100 for fit to THAT persona using its scoring guide. If a listing fits no persona well, still pick the closest and score it low.
Return ONLY a JSON object:
{{"analyses": [{{"item_id": <the listing's item_id>, "persona": "<exactly one persona name>", "score": <0-100>, "summary": "<2 sentences>", "notes": "<why it fits that persona or not>"}}, ...]}}
Include exactly one analysis per listing and echo each listing's item_id. Be concise and honest.
Score 90+ = excellent fit, 70-89 = good, 50-69 = ok, below 50 = weak."""
