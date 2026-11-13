import asyncio
import json
import os
import time
from typing import Dict, List, Optional

from google import genai
from google.genai import types as genai_types
from google.genai.types import UploadFileConfig
from pydantic import BaseModel, Field


class SceneCandidate(BaseModel):
    scene_id: str = Field(description="Short stable identifier like A1, A2, A3.")
    slugline: str = Field(description="Screenplay-style heading (INT/EXT + place + time).")
    scene_summary: str = Field(description="What happens in this scene, 2-4 sentences.")
    action_beats: List[str] = Field(description="3-6 concrete visual action beats.")
    signature_dialogue: List[str] = Field(description="1-4 short quoted lines from script.")
    props_motifs: List[str] = Field(description="3-6 specific objects/symbols/motifs.")
    visual_atmosphere: str = Field(description="Lighting, camera energy, rhythm, mood cues.")
    transition_hooks: List[str] = Field(description="2-4 details that can bridge into another movie scene.")
    script_excerpt: str = Field(description="A 90-180 word excerpt grounded in screenplay language.")


class SceneExtractionOutput(BaseModel):
    candidates: List[SceneCandidate] = Field(description="2-3 iconic scene candidates ranked by recognizability.")


class SeamChoice(BaseModel):
    scene_id_a: str = Field(description="Chosen scene_id from movie A.")
    scene_id_b: str = Field(description="Chosen scene_id from movie B.")
    pivot_point: str = Field(description="Single concrete bridge trigger detail.")
    seam_rationale: str = Field(description="Why these scenes create the strongest bridge.")


class SceneOption(BaseModel):
    option_id: str = Field(description="Stable identifier like opt_1, opt_2, opt_3.")
    scene_id_a: str = Field(description="scene_id from movie A.")
    scene_id_b: str = Field(description="scene_id from movie B.")
    title: str = Field(description="Short punchy label for this transition, 4-8 words.")
    pitch: str = Field(description="2-3 sentence description of the continuous transition.")
    pivot_point: str = Field(description="The shared sensory detail that bridges the two scenes.")
    slugline_a: str = Field(description="Slugline of the scene from movie A.")
    slugline_b: str = Field(description="Slugline of the scene from movie B.")
    tone: str = Field(description="Emotional arc summary, e.g. 'Dread to Wonder'.")


class SceneOptionsOutput(BaseModel):
    options: List[SceneOption] = Field(description="3-4 ranked scene transition options.")


class RemixOutput(BaseModel):
    transition_scene_a: str
    pivot_point: str
    visual_transition_advice: str
    target_scene_b: str
    script_remix: str
    image_prompt: str
    first_frame_prompt: str
    last_frame_prompt: str
    video_prompt: str
    grounding_details: List[str]


class RemixEngine:
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY not found in environment")
        self.client = genai.Client(api_key=self.api_key)
        self.script_cache: Dict[str, str] = {}
        self.max_candidates_per_movie = 3
        self.max_instruction_chars = 700
        self.iconic_scenes_dir = os.path.join("scripts_library", "iconic_scenes_json")
        self.iconic_scenes_index = self._load_iconic_scenes_index()
        self.video_model = os.environ.get("VIDEO_MODEL", "veo-3.1-fast-generate-preview")
        self.video_duration_seconds = int(os.environ.get("VIDEO_DURATION_SECONDS", "4"))
        self.video_aspect_ratio = os.environ.get("VIDEO_ASPECT_RATIO", "16:9")
        self.video_resolution = os.environ.get("VIDEO_RESOLUTION", "720p")
        self.video_negative_prompt = os.environ.get(
            "VIDEO_NEGATIVE_PROMPT",
            "cartoon, drawing, low quality, blurry, watermark, text overlay, deformed faces",
        )
        # "interpolation": generate an opening and closing keyframe, then have Veo
        # animate between them. "reference": text prompt + per-film reference images.
        self.video_mode = os.environ.get("VIDEO_MODE", "interpolation").lower()
        self.image_model = os.environ.get("IMAGE_MODEL", "gemini-2.5-flash-image")
        self.use_concept_art = os.environ.get("USE_CONCEPT_ART", "false").lower() == "true"
        self.use_reference_images = os.environ.get("USE_REFERENCE_IMAGES", "true").lower() == "true"
        self.reference_images_dir = os.path.join("scripts_library", "reference_images")
        self.reference_manifest_index = self._load_reference_manifest_index()
        self._downloading: set = set()
        self._failed: set = set()
        self._job_meta: Dict[str, dict] = {}
        self._retry_map: Dict[str, str] = {}
        self._fail_reasons: Dict[str, str] = {}

    def _normalize_movie_key(self, movie_name: str) -> str:
        return movie_name.strip().lower().replace(" ", "_")

    def _load_iconic_scenes_index(self) -> Dict[str, List[SceneCandidate]]:
        index: Dict[str, List[SceneCandidate]] = {}
        if not os.path.isdir(self.iconic_scenes_dir):
            return index

        for filename in os.listdir(self.iconic_scenes_dir):
            if not filename.endswith(".json"):
                continue
            file_path = os.path.join(self.iconic_scenes_dir, filename)
            try:
                with open(file_path, "r", encoding="utf-8") as file_handle:
                    payload = json.load(file_handle)
                scenes = payload.get("scenes", [])
                normalized: List[SceneCandidate] = []
                for scene in scenes:
                    action_beats = scene.get("visual_beats", [])
                    signature_dialogue = scene.get("signature_dialogue", [])
                    props = scene.get("key_props", [])
                    atmosphere_parts = [
                        " / ".join(scene.get("audio_beats", [])[:3]),
                        scene.get("prompt_blueprint", {}).get("image_prompt_seed", ""),
                    ]
                    scene_summary_seed = (
                        " ".join(action_beats[:2]).strip()
                        or scene.get("script_excerpt", "")[:220]
                    )
                    normalized.append(
                        SceneCandidate(
                            scene_id=scene.get("scene_id", "scene_01"),
                            slugline=scene.get("slugline", "INT. UNKNOWN - DAY"),
                            scene_summary=scene_summary_seed,
                            action_beats=action_beats[:6],
                            signature_dialogue=signature_dialogue[:4],
                            props_motifs=props[:6],
                            visual_atmosphere=" | ".join([part for part in atmosphere_parts if part]),
                            transition_hooks=scene.get("transition_hooks", [])[:4],
                            script_excerpt=scene.get("script_excerpt", ""),
                        )
                    )
                movie_title = payload.get("movie_title", "")
                source_file = payload.get("source_file", "")
                file_stem = filename.replace(".iconic_scenes.json", "").replace(".json", "")
                keys = {
                    self._normalize_movie_key(movie_title.replace("_", " ")),
                    self._normalize_movie_key(source_file.replace(".txt", "").replace("_", " ")),
                    self._normalize_movie_key(file_stem),
                }
                for key in keys:
                    if key:
                        index[key] = normalized
            except Exception as parse_error:
                print(f"Failed to load iconic scenes from {file_path}: {parse_error}")
        return index

    def _get_cached_json_scenes(self, movie_name: str) -> List[SceneCandidate]:
        return self.iconic_scenes_index.get(self._normalize_movie_key(movie_name), [])

    def _load_reference_manifest_index(self) -> Dict[str, dict]:
        index: Dict[str, dict] = {}
        if not os.path.isdir(self.reference_images_dir):
            return index

        for folder_name in os.listdir(self.reference_images_dir):
            folder_path = os.path.join(self.reference_images_dir, folder_name)
            if not os.path.isdir(folder_path):
                continue
            manifest_path = os.path.join(folder_path, "manifest.json")
            if not os.path.exists(manifest_path):
                continue
            try:
                with open(manifest_path, "r", encoding="utf-8") as handle:
                    manifest = json.load(handle)
                keys = {
                    self._normalize_movie_key(folder_name),
                    self._normalize_movie_key(manifest.get("movie_key", "")),
                    self._normalize_movie_key(manifest.get("movie_title", "")),
                    self._normalize_movie_key(
                        manifest.get("source_json", "").replace(".iconic_scenes.json", "").replace(".json", "")
                    ),
                }
                manifest["base_dir"] = folder_path
                for key in keys:
                    if key:
                        index[key] = manifest
            except Exception as manifest_error:
                print(f"Failed loading reference manifest {manifest_path}: {manifest_error}")
        return index

    def _get_reference_manifest(self, movie_name: str) -> Optional[dict]:
        return self.reference_manifest_index.get(self._normalize_movie_key(movie_name))

    def _make_reference_asset(self, manifest: dict, role: str):
        for asset in manifest.get("assets", []):
            if asset.get("role") != role:
                continue
            filename = asset.get("filename")
            if not filename:
                continue
            image_path = os.path.join(manifest.get("base_dir", ""), filename)
            if not os.path.exists(image_path):
                continue
            image_obj = genai_types.Image.from_file(location=image_path)
            return genai_types.VideoGenerationReferenceImage(
                image=image_obj,
                reference_type="asset",
            )
        return None

    def _select_reference_images(self, movie_a: str, movie_b: str):
        if not self.use_reference_images:
            return []

        manifest_a = self._get_reference_manifest(movie_a)
        manifest_b = self._get_reference_manifest(movie_b)
        if not manifest_a or not manifest_b:
            return []

        selected = []
        for manifest, role in [
            (manifest_a, "character_primary"),
            (manifest_b, "character_primary"),
            (manifest_a, "hero_prop_setting"),
        ]:
            try:
                reference = self._make_reference_asset(manifest, role)
                if reference is not None:
                    selected.append(reference)
            except Exception as reference_error:
                print(f"Failed to load reference image ({role}): {reference_error}")

        # Veo supports up to 3 reference images.
        return selected[:3]

    def _build_style_report(self, movie_name: str, scenes: List[SceneCandidate]) -> str:
        if not scenes:
            return f"{movie_name}: No style profile available."
        selected = scenes[:2]
        details = []
        for scene in selected:
            details.append(
                f"{scene.slugline} | Beats: {', '.join(scene.action_beats[:3])} | Atmosphere: {scene.visual_atmosphere}"
            )
        return f"{movie_name} style profile from iconic scene JSON: " + " || ".join(details)

    def _get_or_create_cache(self, script_name: str, script_path: str):
        if script_name in self.script_cache:
            return self.script_cache[script_name]
        print(f"Uploading and caching {script_name}...")
        uploaded_file = self.client.files.upload(
            file=script_path,
            config=UploadFileConfig(display_name=script_name),
        )
        while uploaded_file.state.name == "PROCESSING":
            time.sleep(2)
            uploaded_file = self.client.files.get(name=uploaded_file.name)
        cache = self.client.caches.create(
            model="models/gemini-2.0-flash",
            config={"contents": [uploaded_file], "ttl": "3600s"},
        )
        self.script_cache[script_name] = cache.name
        return cache.name

    @staticmethod
    def _truncate_text(value: str, limit: int) -> str:
        if not value:
            return ""
        if len(value) <= limit:
            return value
        return value[:limit].rstrip() + "..."

    @staticmethod
    def _has_substance(items: List[str], minimum: int = 1) -> bool:
        return len([item for item in items if item and item.strip()]) >= minimum

    def _scene_is_weak(self, scene: SceneCandidate) -> bool:
        return (
            len(scene.scene_summary.strip()) < 50
            or not self._has_substance(scene.action_beats, minimum=2)
            or not self._has_substance(scene.signature_dialogue, minimum=1)
            or not self._has_substance(scene.props_motifs, minimum=2)
            or len(scene.script_excerpt.strip()) < 80
        )

    def _scene_for_prompt(self, scene: SceneCandidate) -> dict:
        return {
            "scene_id": scene.scene_id,
            "slugline": scene.slugline,
            "scene_summary": self._truncate_text(scene.scene_summary, 450),
            "action_beats": scene.action_beats[:5],
            "signature_dialogue": scene.signature_dialogue[:4],
            "props_motifs": scene.props_motifs[:6],
            "visual_atmosphere": self._truncate_text(scene.visual_atmosphere, 320),
            "transition_hooks": scene.transition_hooks[:4],
            "script_excerpt": self._truncate_text(scene.script_excerpt, 650),
        }

    async def identify_iconic_scenes(
        self, movie_name: str, cache_name: str, strict: bool = False
    ) -> List[SceneCandidate]:
        strict_addendum = (
            "\nSTRICT MODE: Reject vague/generalized descriptions. "
            "Every candidate must include concrete props, specific dialogue fragments, and visual actions."
            if strict
            else ""
        )
        prompt = f"""
You are a screenplay analyst.
Movie: {movie_name}

Task:
Return exactly 3 iconic scene candidates from this movie's script.
Prioritize scenes that audiences immediately recognize.

For each candidate:
- Keep screenplay faithfulness high.
- Include signature dialogue fragments and physically specific props.
- Provide visual rhythm/camera/lighting cues implied by the script language.
- Include a script excerpt (90-180 words) grounded in the source screenplay.
- Avoid actor names; refer to characters only.
{strict_addendum}
"""
        response = await self.client.aio.models.generate_content(
            model="models/gemini-2.0-flash",
            contents=[prompt],
            config={
                "cached_content": cache_name,
                "response_mime_type": "application/json",
                "response_schema": SceneExtractionOutput,
            },
        )
        parsed = response.parsed
        if not parsed or not parsed.candidates:
            return []
        return parsed.candidates[: self.max_candidates_per_movie]

    async def _get_grounded_scene_candidates(self, movie_name: str, cache_name: Optional[str]) -> List[SceneCandidate]:
        json_candidates = self._get_cached_json_scenes(movie_name)
        if json_candidates:
            strong = [scene for scene in json_candidates if not self._scene_is_weak(scene)]
            if strong:
                return strong[: self.max_candidates_per_movie]
            return json_candidates[: self.max_candidates_per_movie]

        if not cache_name:
            return []

        candidates = await self.identify_iconic_scenes(movie_name, cache_name, strict=False)
        strong_candidates = [scene for scene in candidates if not self._scene_is_weak(scene)]
        if len(strong_candidates) < 2:
            retry_candidates = await self.identify_iconic_scenes(movie_name, cache_name, strict=True)
            retry_strong = [scene for scene in retry_candidates if not self._scene_is_weak(scene)]
            if retry_strong:
                return retry_strong
            if retry_candidates:
                return retry_candidates
        if strong_candidates:
            return strong_candidates
        return candidates

    async def _select_best_seam_pair(
        self,
        movie_a: str,
        movie_b: str,
        instruction: str,
        scenes_a: List[SceneCandidate],
        scenes_b: List[SceneCandidate],
    ):
        compact_a = [self._scene_for_prompt(scene) for scene in scenes_a]
        compact_b = [self._scene_for_prompt(scene) for scene in scenes_b]
        instruction_trimmed = self._truncate_text(instruction, self.max_instruction_chars)
        prompt = f"""
You are selecting the strongest cinematic transition point between two films.
The goal is NOT a mashup or collage. Instead, find the moment where Scene A can
NATURALLY HAND OFF to Scene B — as if the same cinematographer shot a single
continuous sequence that begins in one film's world and ends in the other's.

User instruction: {instruction_trimmed}

Movie A: {movie_a}
Candidates A (JSON):
{json.dumps(compact_a, ensure_ascii=True)}

Movie B: {movie_b}
Candidates B (JSON):
{json.dumps(compact_b, ensure_ascii=True)}

Choose one scene from each side. The winning pair should:
1) Share a concrete visual or emotional throughline (a gesture, an object, a lighting state, or an emotional beat that exists in both scenes).
2) Allow Scene A to reach a natural pause or inflection point where the camera/audio can seamlessly carry the viewer into Scene B.
3) Maintain tonal continuity — the emotional arc should feel like one rising or falling line, not two separate moments stitched together.
4) Maximize recognizability so audiences feel both source films.
"""
        response = await self.client.aio.models.generate_content(
            model="models/gemini-2.0-flash",
            contents=[prompt],
            config={
                "response_mime_type": "application/json",
                "response_schema": SeamChoice,
            },
        )
        parsed = response.parsed
        if not parsed:
            return scenes_a[0], scenes_b[0], "Iconic-object match cut", "Fallback seam selection."
        scene_a = next((s for s in scenes_a if s.scene_id == parsed.scene_id_a), scenes_a[0])
        scene_b = next((s for s in scenes_b if s.scene_id == parsed.scene_id_b), scenes_b[0])
        return scene_a, scene_b, parsed.pivot_point, parsed.seam_rationale

    async def generate_scene_options(self, movie_a: str, movie_b: str) -> List[SceneOption]:
        cache_a = None
        cache_b = None
        if not self._get_cached_json_scenes(movie_a):
            path_a = os.path.join("scripts_library", f"{movie_a.replace(' ', '_')}.txt")
            cache_a = await asyncio.to_thread(self._get_or_create_cache, movie_a, path_a)
        if not self._get_cached_json_scenes(movie_b):
            path_b = os.path.join("scripts_library", f"{movie_b.replace(' ', '_')}.txt")
            cache_b = await asyncio.to_thread(self._get_or_create_cache, movie_b, path_b)

        scenes_a, scenes_b = await asyncio.gather(
            self._get_grounded_scene_candidates(movie_a, cache_a),
            self._get_grounded_scene_candidates(movie_b, cache_b),
        )
        if not scenes_a or not scenes_b:
            raise ValueError("Could not extract grounded scene candidates.")

        all_scenes_a = self._get_cached_json_scenes(movie_a) or scenes_a
        all_scenes_b = self._get_cached_json_scenes(movie_b) or scenes_b

        compact_a = [self._scene_for_prompt(s) for s in all_scenes_a]
        compact_b = [self._scene_for_prompt(s) for s in all_scenes_b]

        prompt = f"""
You are a cinematic transition architect. Given iconic scenes from two films,
propose 3-4 distinct TRANSITION OPTIONS — each a different way to create ONE
CONTINUOUS SEQUENCE that begins inside a scene from Movie A and flows naturally
into a scene from Movie B.

Each option should pair a DIFFERENT combination of scenes. Do NOT repeat the
same pairing. Explore varied emotional arcs and transition styles.

Movie A: {movie_a}
Available Scenes A (JSON):
{json.dumps(compact_a, ensure_ascii=True)}

Movie B: {movie_b}
Available Scenes B (JSON):
{json.dumps(compact_b, ensure_ascii=True)}

For each option:
- title: A short evocative label (4-8 words) like a chapter heading.
- pitch: 2-3 sentences describing how Scene A flows into Scene B. Mention
  specific props, gestures, or dialogue from each scene. Explain the transition
  mechanism (match-cut, sound bridge, camera drift, etc.).
- pivot_point: The single shared sensory detail that bridges the two scenes.
- tone: The emotional arc in 2-4 words, e.g. "Isolation to Brotherhood".
- scene_id_a, scene_id_b: The scene_ids from the JSON above.
- slugline_a, slugline_b: The sluglines from the JSON above.

Rank options by how seamless and cinematically satisfying the transition would be.
Each option must feel like one scene, not two clips stitched together.
"""
        response = await self.client.aio.models.generate_content(
            model="models/gemini-2.0-flash",
            contents=[prompt],
            config={
                "response_mime_type": "application/json",
                "response_schema": SceneOptionsOutput,
            },
        )
        parsed = response.parsed
        if not parsed or not parsed.options:
            return []
        return parsed.options[:4]

    async def suggest_mashup_instruction(self, movie_a: str, movie_b: str):
        cache_a = None
        cache_b = None
        if not self._get_cached_json_scenes(movie_a):
            path_a = os.path.join("scripts_library", f"{movie_a.replace(' ', '_')}.txt")
            cache_a = await asyncio.to_thread(self._get_or_create_cache, movie_a, path_a)
        if not self._get_cached_json_scenes(movie_b):
            path_b = os.path.join("scripts_library", f"{movie_b.replace(' ', '_')}.txt")
            cache_b = await asyncio.to_thread(self._get_or_create_cache, movie_b, path_b)

        scenes_a, scenes_b = await asyncio.gather(
            self._get_grounded_scene_candidates(movie_a, cache_a),
            self._get_grounded_scene_candidates(movie_b, cache_b),
        )
        if not scenes_a or not scenes_b:
            raise ValueError("Could not extract grounded scene candidates for suggestion.")

        selected_a, selected_b, pivot_point, seam_rationale = await self._select_best_seam_pair(
            movie_a, movie_b, "Find the smoothest linear transition between these films.", scenes_a, scenes_b
        )
        prompt = f"""
You are a Hollywood screenwriter crafting ONE instruction sentence for a
scene-transition engine. The engine will produce a SINGLE CONTINUOUS SEQUENCE
that begins inside Scene A and ends inside Scene B — like one unbroken take
that drifts from one film's reality into the other.

Movie A: {movie_a}
Selected Scene A: {json.dumps(self._scene_for_prompt(selected_a), ensure_ascii=True)}

Movie B: {movie_b}
Selected Scene B: {json.dumps(self._scene_for_prompt(selected_b), ensure_ascii=True)}

Seam hint:
- pivot point: {pivot_point}
- rationale: {seam_rationale}

Requirements:
- Exactly one sentence.
- Describe the sequence as a continuous linear flow: Scene A action → transition beat → Scene B action.
- Name a specific prop, gesture, or sensory detail from each movie that anchors the continuity.
- Specify ONE transition mechanism (match-cut, sound bridge, camera drift, rack focus, whip pan, etc.).
- The result must feel like one scene, not two scenes glued together.
- No generic phrasing like "merge worlds" or "blend universes".
"""
        response = await self.client.aio.models.generate_content(
            model="models/gemini-2.0-flash",
            contents=[prompt],
        )
        return response.text.strip()

    @staticmethod
    def _extract_image_from_generate_content(image_response):
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
                image = part.as_image()
            except Exception:
                continue
            if image is not None:
                return image
        return None

    async def _generate_keyframe(self, prompt: str, label: str, stamp: str):
        """Generate one keyframe still. Returns (image, public_url) or (None, None)."""
        full_prompt = (
            "Photorealistic 35mm film still, cinematic lighting, shallow depth of field. "
            "No text, captions, watermarks, logos or borders. "
            + prompt
        )
        try:
            try:
                config = genai_types.GenerateContentConfig(
                    response_modalities=["IMAGE"],
                    image_config=genai_types.ImageConfig(aspect_ratio=self.video_aspect_ratio),
                )
            except Exception:
                config = {"response_modalities": ["IMAGE"]}
            response = await self.client.aio.models.generate_content(
                model=self.image_model,
                contents=full_prompt,
                config=config,
            )
            image_obj = self._extract_image_from_generate_content(response)
            if image_obj is None:
                print(f"Keyframe ({label}) returned no image.")
                return None, None
            filename = f"concept_{stamp}_{label}.png"
            image_obj.save(os.path.join("..", "frontend", "public", filename))
            return image_obj, f"/{filename}"
        except Exception as keyframe_error:
            print(f"Keyframe ({label}) generation failed: {keyframe_error}")
            return None, None

    async def find_seam(
        self, movie_a: str, movie_b: str, instruction: str,
        scene_id_a: Optional[str] = None, scene_id_b: Optional[str] = None,
        pivot_point: Optional[str] = None,
    ):
        user_pivot = (pivot_point or "").strip()
        cache_a = None
        cache_b = None
        if not self._get_cached_json_scenes(movie_a):
            path_a = os.path.join("scripts_library", f"{movie_a.replace(' ', '_')}.txt")
            cache_a = await asyncio.to_thread(self._get_or_create_cache, movie_a, path_a)
        if not self._get_cached_json_scenes(movie_b):
            path_b = os.path.join("scripts_library", f"{movie_b.replace(' ', '_')}.txt")
            cache_b = await asyncio.to_thread(self._get_or_create_cache, movie_b, path_b)

        scenes_a, scenes_b = await asyncio.gather(
            self._get_grounded_scene_candidates(movie_a, cache_a),
            self._get_grounded_scene_candidates(movie_b, cache_b),
        )
        if not scenes_a or not scenes_b:
            raise ValueError("Could not extract grounded scenes from one or both scripts.")

        all_scenes_a = self._get_cached_json_scenes(movie_a) or scenes_a
        all_scenes_b = self._get_cached_json_scenes(movie_b) or scenes_b

        style_a = self._build_style_report(movie_a, scenes_a)
        style_b = self._build_style_report(movie_b, scenes_b)

        if scene_id_a and scene_id_b:
            selected_a = next((s for s in all_scenes_a if s.scene_id == scene_id_a), scenes_a[0])
            selected_b = next((s for s in all_scenes_b if s.scene_id == scene_id_b), scenes_b[0])
            pivot_point = self._truncate_text(user_pivot, 300) or "Use the transition described in the user instruction."
            seam_rationale = "Scenes chosen by user from transition options."
        else:
            selected_a, selected_b, pivot_point, seam_rationale = await self._select_best_seam_pair(
                movie_a, movie_b, instruction, scenes_a, scenes_b
            )

        instruction_trimmed = self._truncate_text(instruction, self.max_instruction_chars)
        selected_a_payload = json.dumps(self._scene_for_prompt(selected_a), ensure_ascii=True)
        selected_b_payload = json.dumps(self._scene_for_prompt(selected_b), ensure_ascii=True)
        style_a_trimmed = self._truncate_text(style_a or "", 650)
        style_b_trimmed = self._truncate_text(style_b or "", 650)
        prompt = f"""
USER INSTRUCTION:
{instruction_trimmed}

You are an elite Hollywood writer-director and multimodal prompt engineer.

CORE PRINCIPLE — LINEAR CONTINUITY, NOT MASHUP:
This is NOT a collage, montage, or side-by-side comparison. You are writing ONE
CONTINUOUS SEQUENCE that begins fully inside Movie A's scene and ends fully
inside Movie B's scene. The transition between them should feel like a single
camera drifting from one reality into another — the way a dream shifts location
while maintaining emotional momentum. The audience should feel the ground
change under their feet mid-scene, not watch two clips stitched together.

STRUCTURE:
  Act 1 (Scene A): We are unmistakably inside Movie A's iconic moment.
  Pivot: A shared sensory detail (object, sound, gesture, light shift) becomes
         the bridge. The camera or soundscape carries us across.
  Act 2 (Scene B): We arrive inside Movie B's iconic moment, and the emotional
         arc that began in Act 1 continues or resolves here.

MOVIE A: {movie_a}
SELECTED SCENE A (JSON):
{selected_a_payload}
STYLE A:
{style_a_trimmed}

MOVIE B: {movie_b}
SELECTED SCENE B (JSON):
{selected_b_payload}
STYLE B:
{style_b_trimmed}

SEAM CHOICE:
- Pivot trigger: {pivot_point}
- Why this seam works: {seam_rationale}

CRITICAL REQUIREMENTS:
1) script_remix must read as ONE continuous screenplay sequence (not two separate scenes):
   - Open with Movie A's slugline and establish the scene with recognizable anchors.
   - Build to the pivot moment where reality shifts.
   - Continue seamlessly into Movie B's world — new slugline only if location changes.
   - Use at least 3 concrete anchors from each source scene (props, gestures, atmosphere).
   - Include action lines, character descriptors, and at most 2 short dialogue fragments per film (<=12 words each).
   - Length: 220-380 words.
2) image_prompt: Describe the PIVOT MOMENT — the single frame where both films coexist. Rich detail: composition, lens, lighting, wardrobe, texture, mood.
3) video_prompt: Describe a SINGLE CONTINUOUS SHOT or sequence. Must include:
   - Camera movement that carries us from Scene A through the pivot into Scene B.
   - Sound design that morphs (not cuts) from one world to the other.
   - Emotional arc as one unbroken line (e.g., dread → wonder, isolation → connection).
   - Pacing cues (slow build, accelerating, etc.).
   - Do NOT describe two separate shots or a montage.
   - CRITICAL: Do NOT use character names, movie titles, actor names, or quoted dialogue.
     Instead, describe each character with HIGHLY SPECIFIC VISUAL DETAILS that make them
     visually recognizable without naming them. Include:
       * Exact clothing (color, fabric, style — e.g. "a man in a rumpled tan suit and
         blue plaid shirt" not just "a man")
       * Distinctive physical features (build, hair, skin, posture)
       * The EXACT iconic prop they are holding or interacting with (e.g. "an open box
         of assorted chocolates on his lap", "holding out a small red pill in one palm
         and a blue pill in the other")
       * The EXACT setting details (e.g. "a white park bench", "a dim room with
         green-tinted light and leather armchairs")
     The goal is that anyone seeing the generated video would IMMEDIATELY recognize the
     scenes without needing names. Be hyper-specific about wardrobe, props, and setting.
4) In script_remix and image_prompt you MAY use character names for authenticity.
   In video_prompt, first_frame_prompt and last_frame_prompt you MUST NOT — but
   compensate with rich visual specificity.
5) first_frame_prompt and last_frame_prompt: two STILL IMAGE descriptions that a
   video model will animate between. The video starts on the first and ends on the last.
   - first_frame_prompt: the opening frame, unmistakably inside Scene A, a moment
     before the pivot. One frozen instant — no motion, no sequence of events.
   - last_frame_prompt: the closing frame, unmistakably inside Scene B, just after
     the pivot has resolved.
   - MATCH-CUT GEOMETRY: the pivot element (the object, hand, face or light source
     that bridges the scenes) must appear in BOTH frames at the same screen position,
     similar scale and the same camera angle, so the motion between them is short
     and readable. State that position explicitly in both (e.g. "centre frame,
     lower third").
   - Use the same shot size and lens in both frames. Each frame keeps its own
     film's palette, wardrobe, props and setting.
   - Same no-names rule and visual specificity as video_prompt. 60-110 words each.
   - video_prompt must describe the motion that carries the first frame into the
     last frame, and must not contradict either frame.
6) Do not be generic in script_remix. Every detail should be specific to these films.
"""
        response = await self.client.aio.models.generate_content(
            model="models/gemini-2.0-flash",
            contents=[prompt],
            config={
                "response_mime_type": "application/json",
                "response_schema": RemixOutput,
            },
        )

        remix_data = response.parsed.model_dump()
        image_prompt = remix_data.get("image_prompt")
        video_prompt = remix_data.get("video_prompt")
        if video_prompt:
            image_obj = None
            if image_prompt and self.use_concept_art:
                try:
                    print(f"Generating Concept Art: {image_prompt}")
                    image_response = await self.client.aio.models.generate_content(
                        model="gemini-2.5-flash-image",
                        contents=image_prompt,
                        config={"response_modalities": ["IMAGE"]},
                    )
                    image_obj = self._extract_image_from_generate_content(image_response)
                    if image_obj is None:
                        print("Concept Art generation returned no image parts; continuing without image guidance.")
                    else:
                        timestamp = int(time.time())
                        image_filename = f"concept_{timestamp}.png"
                        image_save_path = os.path.join("..", "frontend", "public", image_filename)
                        image_obj.save(image_save_path)
                        remix_data["concept_art_url"] = f"/{image_filename}"
                except Exception as image_error:
                    print(f"Concept Art generation failed: {image_error}. Continuing without image guidance.")
            last_frame_obj = None
            first_prompt = remix_data.get("first_frame_prompt")
            last_prompt = remix_data.get("last_frame_prompt")
            want_keyframes = self.video_mode == "interpolation" and first_prompt and last_prompt
            stamp = f"{int(time.time())}_{os.urandom(3).hex()}"
            if want_keyframes:
                sanitized_prompt, (first_obj, first_url), (last_obj, last_url) = await asyncio.gather(
                    self._sanitize_video_prompt(video_prompt),
                    self._generate_keyframe(first_prompt, "first", stamp),
                    self._generate_keyframe(last_prompt, "last", stamp),
                )
                if first_obj is not None and last_obj is not None:
                    image_obj, last_frame_obj = first_obj, last_obj
                    remix_data["keyframe_urls"] = {"first": first_url, "last": last_url}
                    remix_data["concept_art_url"] = first_url
                else:
                    print("Keyframes incomplete; falling back to prompt-only video generation.")
            else:
                sanitized_prompt = await self._sanitize_video_prompt(video_prompt)

            # Veo does not combine first/last frames with reference images.
            reference_images = [] if last_frame_obj is not None else self._select_reference_images(movie_a, movie_b)
            remix_data["video_mode"] = (
                "interpolation" if last_frame_obj is not None
                else "reference" if reference_images
                else "text"
            )
            try:
                operation_name = self.start_forge_video(
                    sanitized_prompt,
                    image=image_obj,
                    last_frame=last_frame_obj,
                    reference_images=reference_images,
                )
                remix_data["video_job_id"] = operation_name
                remix_data["reference_images_used"] = len(reference_images)
            except Exception as video_error:
                print(f"Video forge start failed: {video_error}")
                remix_data["video_error"] = str(video_error)
                remix_data["video_status"] = "failed_to_start"

        remix_data["selected_scene_a"] = selected_a.slugline
        remix_data["selected_scene_b"] = selected_b.slugline
        return remix_data

    async def _sanitize_video_prompt(self, prompt: str) -> str:
        """Rewrite a video prompt to remove character names, movie titles,
        copyrighted dialogue, and any references that could trigger safety
        filters. Keeps all cinematic direction intact."""
        sanitize_prompt = f"""Rewrite the video generation prompt below so it contains
ZERO character names, ZERO movie titles, ZERO actor names, ZERO quoted dialogue.

CRITICAL — you must INCREASE visual specificity, not decrease it:
- Replace every character name with an EXTREMELY DETAILED physical description:
  * Their EXACT outfit (color, fabric, fit — "rumpled tan suit with a blue plaid
    shirt" not "a man in a suit")
  * Their EXACT build, hair, skin tone, posture, facial hair
  * The EXACT prop they hold or interact with ("an open heart-shaped box of assorted
    chocolates resting on his lap", "a small red capsule in his right palm and a
    small blue capsule in his left")
  * Their EXACT setting ("sitting on a white-painted wooden park bench",
    "standing in a dim concrete room bathed in green-tinted fluorescent light")
- The rewritten prompt must be SO visually specific that a reader would immediately
  picture the exact iconic scene without any names being mentioned.
- Remove or rephrase dialogue into described action (e.g. "he speaks earnestly
  about life's unpredictability" instead of quoting).
- Remove movie titles entirely.
- Keep ALL camera direction, shot types, pacing, sound design, lighting, and
  emotional arc EXACTLY as written.
- Keep the same length or make it LONGER with added visual detail.
- NEVER use vague descriptors like "a man", "the figure", "a person". Always
  specify what they look like, what they wear, what they hold.

ORIGINAL PROMPT:
{prompt}

REWRITTEN PROMPT (no names, no titles, no dialogue — but hyper-specific visuals):"""
        try:
            response = await self.client.aio.models.generate_content(
                model="models/gemini-2.0-flash",
                contents=[sanitize_prompt],
            )
            sanitized = response.text.strip()
            if len(sanitized) > 50:
                print(f"Sanitized video prompt: {sanitized}")
                return sanitized
        except Exception as e:
            print(f"Video prompt sanitization failed: {e}. Using original.")
        return prompt

    def start_forge_video(self, prompt: str, image=None, reference_images=None, is_retry=False, last_frame=None):
        print(f"Starting Video Forge{' (retry)' if is_retry else ''} with {self.video_model}: {prompt}")
        reference_images = reference_images or []
        person_generation = "allow_adult" if (image is not None or reference_images) else "allow_all"
        duration_seconds = self.video_duration_seconds
        if last_frame is not None and image is None:
            last_frame = None  # last_frame is only valid together with a first frame
        if last_frame is not None:
            reference_images = []
        if (reference_images or last_frame is not None) and duration_seconds < 8:
            duration_seconds = 8
        is_veo3_model = self.video_model.startswith("veo-3")

        config_kwargs = {
            "aspect_ratio": self.video_aspect_ratio,
            "resolution": self.video_resolution,
        }
        if not reference_images:
            config_kwargs["negative_prompt"] = self.video_negative_prompt
        if not is_veo3_model:
            config_kwargs["duration_seconds"] = str(duration_seconds)
            config_kwargs["person_generation"] = person_generation
        if reference_images:
            config_kwargs["reference_images"] = reference_images
        if last_frame is not None:
            config_kwargs["last_frame"] = last_frame

        kwargs = {
            "model": self.video_model,
            "prompt": prompt,
            "config": genai_types.GenerateVideosConfig(**config_kwargs),
        }
        if image:
            kwargs["image"] = image
        _PARAM_ALIASES = {
            "negative_prompt": ["negative_prompt", "negative prompt", "negativePrompt"],
            "resolution": ["resolution"],
            "duration_seconds": ["duration_seconds", "durationSeconds", "duration"],
            "person_generation": ["person_generation", "personGeneration"],
            "reference_images": ["reference_images", "referenceImages", "reference image"],
            "last_frame": ["last_frame", "lastFrame", "last frame"],
        }

        def _detect_unsupported(msg: str) -> Optional[str]:
            msg_lower = msg.lower()
            for param, aliases in _PARAM_ALIASES.items():
                if any(alias.lower() in msg_lower for alias in aliases):
                    return param
            return None

        def _retry_without(param: str):
            print(f"Retrying video forge without {param} parameter.")
            config_kwargs.pop(param, None)
            kwargs["config"] = genai_types.GenerateVideosConfig(**config_kwargs)
            return self.client.models.generate_videos(**kwargs)

        try:
            operation = self.client.models.generate_videos(**kwargs)
        except Exception as e:
            param = _detect_unsupported(str(e))
            if param and param in config_kwargs:
                try:
                    operation = _retry_without(param)
                except Exception as e2:
                    param2 = _detect_unsupported(str(e2))
                    if param2 and param2 in config_kwargs:
                        operation = _retry_without(param2)
                    else:
                        raise
            else:
                raise

        safe_name = operation.name.replace("/", "_")
        if not is_retry:
            # A filtered keyframe job retries from text alone: the frames may be the trigger.
            self._job_meta[safe_name] = {"prompt": prompt, "image": None if last_frame is not None else image}
        return operation.name

    def poll_video_job(self, operation_name: str):
        from google.genai import types

        if operation_name.replace("/", "_") in self._retry_map:
            operation_name = self._retry_map[operation_name.replace("/", "_")]

        safe_name = operation_name.replace("/", "_")
        local_path = os.path.join("..", "frontend", "public", f"remix_{safe_name}.mp4")

        orig_safe = [k for k, v in self._retry_map.items() if v == operation_name]
        for osn in orig_safe:
            orig_path = os.path.join("..", "frontend", "public", f"remix_{osn}.mp4")
            if os.path.exists(orig_path) and os.path.getsize(orig_path) > 0:
                size_mb = os.path.getsize(orig_path) / (1024 * 1024)
                print(f"Video ready on disk ({size_mb:.1f} MB): {orig_path}")
                return f"/remix_{osn}.mp4"

        if os.path.exists(local_path) and os.path.getsize(local_path) > 0:
            size_mb = os.path.getsize(local_path) / (1024 * 1024)
            print(f"Video ready on disk ({size_mb:.1f} MB): {local_path}")
            return f"/remix_{safe_name}.mp4"

        if safe_name in self._downloading:
            print("Video download in progress...")
            return None

        if safe_name in self._failed:
            return "error"

        operation = types.GenerateVideosOperation(name=operation_name)
        operation = self.client.operations.get(operation)
        if operation.done:
            if hasattr(operation.response, "generated_videos") and operation.response.generated_videos:
                print(f"Video generation complete. Starting download...")
                self._downloading.add(safe_name)
                import threading
                def _download():
                    try:
                        vid = operation.response.generated_videos[0]
                        self.client.files.download(file=vid.video)
                        vid.video.save(local_path)
                        size_mb = os.path.getsize(local_path) / (1024 * 1024)
                        print(f"Video downloaded successfully ({size_mb:.1f} MB)")
                    except Exception as e:
                        print(f"Video download failed: {e}")
                    finally:
                        self._downloading.discard(safe_name)
                threading.Thread(target=_download, daemon=True).start()
                return None

            op_error = getattr(operation, "error", None)
            if op_error:
                message = op_error.get("message") if isinstance(op_error, dict) else str(op_error)
                print(f"Video generation failed: {message}")
                self._fail_reasons[safe_name] = f"Video generation failed: {message}"
                self._failed.add(safe_name)
                return "error"

            reason = getattr(operation.response, "rai_media_filtered_reasons", None)
            print(f"Video filtered. Reason: {reason or 'unknown (likely safety filter)'}.")

            meta = self._job_meta.get(safe_name)
            if meta and safe_name not in self._failed:
                print("Auto-retrying with abstract prompt (no keyframes or reference images)...")
                try:
                    abstract_prompt = self._make_abstract_retry_prompt(meta["prompt"])
                    retry_op_name = self.start_forge_video(
                        abstract_prompt, image=meta.get("image"), reference_images=None,
                        is_retry=True,
                    )
                    orig_request_safe = safe_name
                    for k, v in list(self._retry_map.items()):
                        if v == operation_name:
                            orig_request_safe = k
                            break
                    self._retry_map[orig_request_safe] = retry_op_name
                    print(f"Retry job started: {retry_op_name}")
                    return None
                except Exception as e:
                    print(f"Retry failed to start: {e}")

            reason_text = "; ".join(reason) if isinstance(reason, list) else (str(reason) if reason else "")
            self._fail_reasons[safe_name] = (
                "Video was filtered by safety checks"
                + (f" ({reason_text})" if reason_text else "")
                + ". Try a different transition."
            )
            self._failed.add(safe_name)
            return "error"
        print("Video still generating...")
        return None

    def get_failure_reason(self, operation_name: str) -> Optional[str]:
        safe_name = operation_name.replace("/", "_")
        retry_name = self._retry_map.get(safe_name)
        if retry_name:
            safe_name = retry_name.replace("/", "_")
        return self._fail_reasons.get(safe_name)

    def _make_abstract_retry_prompt(self, prompt: str) -> str:
        """Strip quoted dialogue from the prompt for retry, keeping the visual direction."""
        import re
        # Only double-quoted spans (straight or curly) are dialogue. Single quotes are
        # left alone: they are almost always apostrophes ("the man's suit").
        result = re.sub(r'"[^"]*"', '', prompt)
        result = re.sub(r'\u201c[^\u201d]*\u201d', '', result)
        result = re.sub(r'\s+', ' ', result).strip()
        prefix = ("A cinematic single-take transition sequence. "
                   "Focus on visual composition, lighting, and camera movement. ")
        return prefix + result if len(result) > 50 else prompt
