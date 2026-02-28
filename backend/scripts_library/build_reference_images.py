import json
import os
from pathlib import Path
from typing import Dict, List, Optional

from google import genai


def extract_image_from_response(image_response):
    parts = []
    if hasattr(image_response, "parts") and image_response.parts:
        parts = image_response.parts
    elif hasattr(image_response, "candidates") and image_response.candidates:
        first_candidate = image_response.candidates[0]
        if (
            hasattr(first_candidate, "content")
            and first_candidate.content
            and hasattr(first_candidate.content, "parts")
            and first_candidate.content.parts
        ):
            parts = first_candidate.content.parts

    for part in parts:
        try:
            return part.as_image()
        except Exception:
            continue
    return None


def normalize_movie_key(value: str) -> str:
    return value.strip().lower().replace(" ", "_")


def pick_assets(scene_payload: Dict) -> List[Dict]:
    scenes = scene_payload.get("scenes", [])
    if not scenes:
        return []

    scene_a = scenes[0]
    scene_b = scenes[1] if len(scenes) > 1 else scenes[0]

    chars_a = scene_a.get("characters", [])
    chars_b = scene_b.get("characters", [])
    props_a = scene_a.get("key_props", [])
    slug_a = scene_a.get("slugline", "INT. UNKNOWN - DAY")

    primary_char = chars_a[0] if chars_a else "the protagonist"
    secondary_char = chars_b[1] if len(chars_b) > 1 else (chars_b[0] if chars_b else "the secondary character")
    prop_anchor = props_a[0] if props_a else "an iconic set piece"

    prompt_seed_a = scene_a.get("prompt_blueprint", {}).get("image_prompt_seed", "")
    prompt_seed_b = scene_b.get("prompt_blueprint", {}).get("image_prompt_seed", "")

    return [
        {
            "role": "character_primary",
            "filename": "character_primary.png",
            "prompt": (
                f"Cinematic character reference portrait of {primary_char}. "
                f"{prompt_seed_a} Keep neutral background, full facial detail, high realism, no text."
            ).strip(),
        },
        {
            "role": "character_secondary",
            "filename": "character_secondary.png",
            "prompt": (
                f"Cinematic character reference portrait of {secondary_char}. "
                f"{prompt_seed_b} Keep neutral background, high realism, no text."
            ).strip(),
        },
        {
            "role": "hero_prop_setting",
            "filename": "hero_prop_setting.png",
            "prompt": (
                f"High-detail reference image of {prop_anchor} in {slug_a}. "
                "No characters unless required by scene identity. High realism, no text."
            ).strip(),
        },
    ]


def main():
    base_dir = Path(__file__).resolve().parent
    json_dir = base_dir / "iconic_scenes_json"
    out_root = base_dir / "reference_images"
    out_root.mkdir(exist_ok=True)

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise SystemExit("GEMINI_API_KEY missing. Export it or source .env before running.")

    client = genai.Client(api_key=api_key)

    json_files = sorted(json_dir.glob("*.json"))
    if not json_files:
        raise SystemExit(f"No JSON files found in {json_dir}")

    for json_file in json_files:
        with open(json_file, "r", encoding="utf-8") as handle:
            payload = json.load(handle)

        movie_title = payload.get("movie_title", json_file.stem.replace(".iconic_scenes", ""))
        movie_key = normalize_movie_key(movie_title)
        movie_dir = out_root / movie_key
        movie_dir.mkdir(parents=True, exist_ok=True)

        assets = pick_assets(payload)
        manifest = {
            "movie_title": movie_title,
            "movie_key": movie_key,
            "source_json": json_file.name,
            "assets": [],
        }

        print(f"Building references for {movie_title}...")
        for asset in assets:
            output_path = movie_dir / asset["filename"]
            asset_entry = {
                "role": asset["role"],
                "filename": asset["filename"],
                "prompt": asset["prompt"],
                "status": "pending",
            }
            try:
                response = client.models.generate_content(
                    model="gemini-2.5-flash-image",
                    contents=asset["prompt"],
                    config={"response_modalities": ["IMAGE"]},
                )
                image_obj = extract_image_from_response(response)
                if image_obj is None:
                    asset_entry["status"] = "failed_no_image"
                else:
                    image_obj.save(output_path)
                    asset_entry["status"] = "ok"
                    asset_entry["path"] = str(output_path)
            except Exception as gen_error:
                asset_entry["status"] = "failed_exception"
                asset_entry["error"] = str(gen_error)

            manifest["assets"].append(asset_entry)

        manifest_path = movie_dir / "manifest.json"
        with open(manifest_path, "w", encoding="utf-8") as handle:
            json.dump(manifest, handle, indent=2, ensure_ascii=True)
        print(f"Wrote {manifest_path}")

    print("Reference image generation complete.")


if __name__ == "__main__":
    main()
