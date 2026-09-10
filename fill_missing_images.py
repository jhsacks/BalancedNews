import os
import re
import json
import base64
import hashlib
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from openai import OpenAI

ROOT = Path(__file__).parent
DATA = ROOT / "data/briefings"
IMAGE_DIR = DATA / "generated_images"
IMAGE_DIR.mkdir(parents=True, exist_ok=True)

EDITION = os.getenv("BRIEF_EDITION", "").upper()
MAX_IMAGES = int(os.getenv("MAX_GENERATED_IMAGES", "10"))
MODEL = os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-1-mini")
REPO = os.getenv("GITHUB_REPOSITORY", "")
BRANCH = os.getenv("GITHUB_REF_NAME", "main") or "main"


def slug(text):
    value = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:48]
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:10]
    return f"{value or 'story'}-{digest}"


def latest_briefing():
    candidates = []
    for path in DATA.glob("*.json"):
        try:
            payload = json.loads(path.read_text())
            if EDITION and str(payload.get("edition", "")).upper() != EDITION:
                continue
            candidates.append((datetime.fromisoformat(payload["generated_at"]), path, payload))
        except Exception:
            continue
    if not candidates:
        raise RuntimeError("No generated briefing JSON was found for image completion.")
    return max(candidates, key=lambda item: item[0])[1:]


def prompt_for(story, variation):
    headline = str(story.get("headline", ""))
    category = str(story.get("category", "News"))
    palettes = [
        "navy, teal, warm gold", "deep blue, coral, ivory", "forest green, sky blue, amber",
        "charcoal, cobalt, soft orange", "burgundy, slate, pale gold", "indigo, turquoise, sand"
    ]
    compositions = [
        "wide cinematic documentary composition", "editorial still-life composition",
        "architectural and environmental composition", "symbolic objects in a realistic setting",
        "dynamic wide-angle scene", "layered newsroom-magazine composition"
    ]
    return (
        f"Create a unique, polished editorial news illustration for the category {category}. "
        f"Use the story only as thematic context: {headline}. "
        "Translate the subject into a non-personal symbolic or environmental scene. "
        "Do not depict or imitate any named person, politician, celebrity, athlete, logo, trademark, "
        "uniform insignia, national flag, violence, injury, or readable text. "
        f"Use {compositions[variation % len(compositions)]} with a {palettes[variation % len(palettes)]} palette. "
        "Photorealistic editorial quality, suitable for a professional balanced-news website, no text, no numbers, no empty space."
    )


def generate_one(client, story, index, date_prefix):
    filename = f"{date_prefix}-{slug(story.get('headline', 'story'))}.webp"
    destination = IMAGE_DIR / filename
    if not destination.exists():
        result = client.images.generate(
            model=MODEL,
            prompt=prompt_for(story, index),
            size="1536x1024",
            quality="low",
            output_format="webp",
            n=1,
        )
        encoded = result.data[0].b64_json
        if not encoded:
            raise RuntimeError("The image API returned no image data.")
        destination.write_bytes(base64.b64decode(encoded))
    if not REPO:
        raise RuntimeError("GITHUB_REPOSITORY is unavailable; cannot construct a durable image URL.")
    url = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/data/briefings/generated_images/{filename}"
    return index, url, "Visual generated with OpenAI for The Balanced Brief."


def main():
    path, briefing = latest_briefing()
    missing = [
        (index, story)
        for index, story in enumerate(briefing.get("stories", []))
        if not str(story.get("image", "")).strip()
    ][:MAX_IMAGES]
    if not missing:
        print("Generated image fallback: no missing story images.")
        return
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    date_prefix = f"{datetime.fromisoformat(briefing['generated_at']):%Y-%m-%d}-{briefing.get('edition','').lower()}"
    completed = 0
    with ThreadPoolExecutor(max_workers=min(3, len(missing))) as pool:
        futures = {
            pool.submit(generate_one, client, story, order, date_prefix): index
            for order, (index, story) in enumerate(missing)
        }
        for future in as_completed(futures):
            story_index = futures[future]
            try:
                _, url, credit = future.result()
                briefing["stories"][story_index]["image"] = url
                briefing["stories"][story_index]["image_credit"] = credit
                briefing["stories"][story_index]["image_source"] = "AI-generated fallback"
                completed += 1
            except Exception as error:
                print(f"Generated image failed for story {story_index}: {error}")
    path.write_text(json.dumps(briefing, indent=2))
    print(f"Generated image fallback completed: {completed} of {len(missing)} missing images filled.")


if __name__ == "__main__":
    main()
