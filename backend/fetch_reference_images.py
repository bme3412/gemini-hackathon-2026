"""
Fetch reference images for each film using Gemini + Google Search grounding.

Uses the Gemini API with the google_search tool to find publicly available
promotional stills, behind-the-scenes photos, and iconic imagery for each
film, then downloads them into the reference_images directories and updates
the manifests.

Usage:
    python fetch_reference_images.py              # all movies
    python fetch_reference_images.py the_matrix    # single movie
"""

import asyncio
import json
import os
import re
import sys
import time
from typing import List, Optional
from urllib.parse import urlparse

import requests
from google import genai
from google.genai import types as genai_types


REFERENCE_IMAGES_DIR = os.path.join("scripts_library", "reference_images")
ICONIC_SCENES_DIR = os.path.join("scripts_library", "iconic_scenes_json")


def load_env():
    for candidate in [os.path.join("..", ".env"), ".env"]:
        path = os.path.abspath(candidate)
        if not os.path.exists(path):
            continue
        with open(path, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k, v = k.strip(), v.strip().strip('"').strip("'")
                if k and k not in os.environ:
                    os.environ[k] = v
        break


def get_movie_context(movie_key: str) -> dict:
    """Load iconic scenes JSON to build richer search queries."""
    scenes_path = os.path.join(ICONIC_SCENES_DIR, f"{movie_key}.iconic_scenes.json")
    if not os.path.exists(scenes_path):
        return {}
    with open(scenes_path, "r") as f:
        return json.load(f)


def build_search_queries(manifest: dict, movie_context: dict) -> List[dict]:
    """Build targeted search queries for each asset role."""
    title = manifest.get("movie_title", "")
    scenes = movie_context.get("scenes", [])

    primary_chars = []
    secondary_chars = []
    key_props = []
    for scene in scenes:
        for c in scene.get("characters", []):
            if c not in primary_chars and c not in secondary_chars:
                if len(primary_chars) < 2:
                    primary_chars.append(c)
                else:
                    secondary_chars.append(c)
        for p in scene.get("key_props", []):
            if p not in key_props:
                key_props.append(p)

    queries = []

    queries.append({
        "role": "character_primary",
        "query": f"{title} movie iconic scene still photograph high resolution",
        "description": f"Iconic still from {title} featuring main characters",
    })

    scene_name = scenes[0].get("scene_name", "") if scenes else ""
    queries.append({
        "role": "character_secondary",
        "query": f"{title} movie {scene_name} scene still photograph" if scene_name else f"{title} movie behind the scenes photograph",
        "description": f"Scene still from {title}",
    })

    prop_str = ", ".join(key_props[:3]) if key_props else "iconic setting"
    queries.append({
        "role": "hero_prop_setting",
        "query": f"{title} movie {prop_str} cinematic still",
        "description": f"Props/setting reference from {title}",
    })

    return queries


def extract_image_urls_from_text(text: str) -> List[str]:
    """Extract URLs from Gemini response that look like image links."""
    url_pattern = r'https?://[^\s\)\"\'<>]+'
    urls = re.findall(url_pattern, text)
    image_extensions = ('.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp')
    image_urls = []
    for url in urls:
        parsed = urlparse(url)
        path_lower = parsed.path.lower()
        if any(path_lower.endswith(ext) for ext in image_extensions):
            image_urls.append(url)
        elif 'image' in url.lower() or 'photo' in url.lower() or 'still' in url.lower():
            image_urls.append(url)
    return image_urls


def extract_urls_from_grounding(response) -> List[str]:
    """Extract source URLs from grounding metadata."""
    urls = []
    try:
        candidates = response.candidates or []
        for candidate in candidates:
            metadata = getattr(candidate, "grounding_metadata", None)
            if not metadata:
                continue
            chunks = getattr(metadata, "grounding_chunks", []) or []
            for chunk in chunks:
                web = getattr(chunk, "web", None)
                if web and hasattr(web, "uri"):
                    urls.append(web.uri)
    except Exception:
        pass
    return urls


def download_image(url: str, save_path: str, timeout: int = 20) -> bool:
    """Download an image from URL (follows redirects), return True on success."""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0.0.0 Safari/537.36",
            "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
        }
        resp = requests.get(
            url, headers=headers, timeout=timeout,
            allow_redirects=True, stream=True,
        )
        if resp.status_code != 200:
            return False
        content_type = resp.headers.get("Content-Type", "")
        if "image" not in content_type and "octet-stream" not in content_type:
            return False
        content = resp.content
        if len(content) < 5000:
            return False
        with open(save_path, "wb") as f:
            f.write(content)
        return True
    except Exception as e:
        print(f"    Download failed for {url[:80]}...: {e}")
        return False


async def fetch_images_for_movie(client: genai.Client, movie_key: str):
    """Use Gemini + Google Search to find and download reference images."""
    manifest_dir = os.path.join(REFERENCE_IMAGES_DIR, movie_key)
    manifest_path = os.path.join(manifest_dir, "manifest.json")

    if not os.path.exists(manifest_path):
        print(f"  No manifest found for {movie_key}, skipping.")
        return

    with open(manifest_path, "r") as f:
        manifest = json.load(f)

    movie_context = get_movie_context(movie_key)
    title = manifest.get("movie_title", movie_key.replace("_", " ").title())
    search_queries = build_search_queries(manifest, movie_context)

    grounding_tool = genai_types.Tool(google_search=genai_types.GoogleSearch())
    config = genai_types.GenerateContentConfig(tools=[grounding_tool])

    updated_assets = []

    for query_info in search_queries:
        role = query_info["role"]
        asset_entry = next(
            (a for a in manifest.get("assets", []) if a.get("role") == role),
            None
        )
        if not asset_entry:
            continue

        existing_file = os.path.join(manifest_dir, asset_entry.get("filename", ""))
        if os.path.exists(existing_file) and os.path.getsize(existing_file) > 5000:
            print(f"  [{role}] Already have image, skipping.")
            asset_entry["status"] = "ok"
            updated_assets.append(asset_entry)
            continue

        prompt = (
            f"Find a high-quality publicly available promotional still or "
            f"cinematic screenshot from the movie \"{title}\". "
            f"I need: {query_info['description']}. "
            f"Search query: {query_info['query']}. "
            f"Return the direct image URL (ending in .jpg, .png, or .webp) "
            f"for the best matching image you can find. "
            f"Provide multiple image URLs if possible, one per line."
        )

        print(f"  [{role}] Searching: {query_info['query']}")
        try:
            response = await client.aio.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt,
                config=config,
            )

            image_urls = extract_image_urls_from_text(response.text or "")
            grounding_urls = extract_urls_from_grounding(response)
            all_urls = image_urls + grounding_urls

            # Deduplicate while preserving order
            seen = set()
            candidate_urls = []
            for u in all_urls:
                if u not in seen:
                    seen.add(u)
                    candidate_urls.append(u)

            filename = asset_entry.get("filename", f"{role}.png")
            save_path = os.path.join(manifest_dir, filename)
            downloaded = False

            for url in candidate_urls[:8]:
                print(f"    Trying: {url[:100]}...")
                if download_image(url, save_path):
                    print(f"    Downloaded successfully.")
                    asset_entry["status"] = "ok"
                    asset_entry["source_url"] = url
                    downloaded = True
                    break

            if not downloaded:
                print(f"    Falling back to Gemini image generation...")
                downloaded = await _generate_fallback_image(
                    client, title, query_info, save_path
                )
                if downloaded:
                    asset_entry["status"] = "generated"
                else:
                    asset_entry["status"] = "failed"
                    print(f"    Could not retrieve image for {role}.")

        except Exception as e:
            print(f"    Search failed for [{role}]: {e}")
            asset_entry["status"] = "failed"

        updated_assets.append(asset_entry)
        time.sleep(1)

    for asset in updated_assets:
        for i, existing in enumerate(manifest.get("assets", [])):
            if existing.get("role") == asset.get("role"):
                manifest["assets"][i] = asset
                break

    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"  Manifest updated: {manifest_path}")


async def _generate_fallback_image(
    client: genai.Client, title: str, query_info: dict, save_path: str
) -> bool:
    """Fall back to Gemini image generation if search-based download fails."""
    try:
        gen_prompt = (
            f"A high-quality cinematic film still inspired by the movie \"{title}\". "
            f"{query_info['description']}. "
            f"Photorealistic, dramatic lighting, film grain, anamorphic lens. "
            f"No text, no watermarks."
        )
        response = await client.aio.models.generate_content(
            model="gemini-2.5-flash-image",
            contents=gen_prompt,
            config=genai_types.GenerateContentConfig(
                response_modalities=["IMAGE"],
            ),
        )
        if response.candidates:
            for part in response.candidates[0].content.parts:
                if hasattr(part, "inline_data") and part.inline_data:
                    data = part.inline_data.data
                    if isinstance(data, str):
                        import base64
                        data = base64.b64decode(data)
                    with open(save_path, "wb") as f:
                        f.write(data)
                    print(f"    Generated fallback image successfully.")
                    return True
    except Exception as e:
        print(f"    Fallback generation failed: {e}")
    return False


async def main(target_keys: Optional[List[str]] = None):
    load_env()
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY not set.")
        sys.exit(1)

    client = genai.Client(api_key=api_key)

    if target_keys:
        movie_keys = target_keys
    else:
        if not os.path.isdir(REFERENCE_IMAGES_DIR):
            print(f"No reference_images directory at {REFERENCE_IMAGES_DIR}")
            sys.exit(1)
        movie_keys = sorted([
            d for d in os.listdir(REFERENCE_IMAGES_DIR)
            if os.path.isdir(os.path.join(REFERENCE_IMAGES_DIR, d))
        ])

    print(f"Fetching reference images for {len(movie_keys)} movies: {', '.join(movie_keys)}\n")

    for key in movie_keys:
        print(f"=== {key.replace('_', ' ').title()} ===")
        await fetch_images_for_movie(client, key)
        print()

    success = 0
    total = 0
    for key in movie_keys:
        manifest_path = os.path.join(REFERENCE_IMAGES_DIR, key, "manifest.json")
        if os.path.exists(manifest_path):
            with open(manifest_path, "r") as f:
                m = json.load(f)
            for a in m.get("assets", []):
                total += 1
                if a.get("status") in ("ok", "generated"):
                    success += 1

    print(f"Done. {success}/{total} reference images retrieved successfully.")


if __name__ == "__main__":
    import functools
    print = functools.partial(print, flush=True)
    targets = sys.argv[1:] if len(sys.argv) > 1 else None
    asyncio.run(main(targets))
