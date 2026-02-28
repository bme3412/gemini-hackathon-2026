import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class SceneSchema(BaseModel):
    scene_name: str = Field(description="Short recognizable scene nickname.")
    slugline: Optional[str] = Field(default=None, description="INT./EXT. location and time cue.")
    characters: List[str] = Field(default_factory=list, description="Primary characters in the scene.")
    key_props: List[str] = Field(default_factory=list, description="Iconic props or motifs.")
    signature_dialogue: List[str] = Field(
        default_factory=list,
        description="Short exact dialogue lines from the source text.",
    )
    visual_beats: List[str] = Field(
        default_factory=list,
        description="Chronological shot/action beats suitable for prompting.",
    )
    audio_beats: List[str] = Field(
        default_factory=list,
        description="Dialogue/SFX/ambience cues suitable for video prompting.",
    )
    transition_hooks: List[str] = Field(
        default_factory=list,
        description="Bridge ideas for scene-to-scene mashups.",
    )
    script_excerpt: str = Field(
        description="Exact scene excerpt (10-40 lines or compact snippet) from source text."
    )


class MovieParseOutput(BaseModel):
    movie_title: str
    source_file: str
    scenes: List[SceneSchema]


class LlamaIntegrationUnavailable(RuntimeError):
    pass


def _load_llama_dependencies():
    """
    Keep imports lazy so the main app can start even if Llama deps aren't installed.
    """
    try:
        from llama_cloud import AsyncLlamaCloud  # type: ignore
        from llama_index.core.workflow import (  # type: ignore
            Context,
            Event,
            StartEvent,
            StopEvent,
            Workflow,
            step,
        )
        return AsyncLlamaCloud, Context, Event, StartEvent, StopEvent, Workflow, step
    except Exception as import_error:  # pragma: no cover
        raise LlamaIntegrationUnavailable(
            "Llama integration dependencies are missing. Install llama-cloud and llama-index-workflows."
        ) from import_error


async def parse_scripts_with_llama(
    scripts_dir: str,
    output_dir: str,
    top_scenes_per_movie: int = 6,
) -> Dict[str, Any]:
    AsyncLlamaCloud, Context, Event, StartEvent, StopEvent, Workflow, step = _load_llama_dependencies()

    api_key = os.getenv("LLAMA_CLOUD_API_KEY")
    if not api_key:
        raise LlamaIntegrationUnavailable("LLAMA_CLOUD_API_KEY is not set.")

    scripts_path = Path(scripts_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    script_files = sorted(scripts_path.glob("*.txt"))
    if not script_files:
        return {"processed": 0, "outputs": [], "message": "No .txt scripts found."}

    class SegmentEvent(Event):
        file_id: str
        source_file: str
        movie_title: str
        category: str
        pages: List[int]

    class ScriptWorkflow(Workflow):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.client = AsyncLlamaCloud(api_key=api_key)

        @step
        async def upload_and_split(self, ev: StartEvent, ctx: Context) -> SegmentEvent:
            uploaded_file = await self.client.files.create(file=ev.file_path, purpose="extract")
            file_id = uploaded_file.id
            movie_title = Path(ev.file_path).stem.replace("_", " ")
            response = await self.client.beta.split.split(
                categories=[
                    {
                        "name": "scene_content",
                        "description": "Narrative screenplay scene content with action/dialogue and scene headings.",
                    },
                    {
                        "name": "index_or_front_matter",
                        "description": "Title pages, legal headers, tables, indexes, and metadata.",
                    },
                    {
                        "name": "other",
                        "description": "Any non-scene content that does not belong to a screenplay scene.",
                    },
                ],
                document_input={"type": "file_id", "value": file_id},
            )
            segments = response.result.segments if response.result else []
            await ctx.store.set("segments_count", len(segments))
            for segment in segments:
                ctx.send_event(
                    SegmentEvent(
                        file_id=file_id,
                        source_file=Path(ev.file_path).name,
                        movie_title=movie_title,
                        category=segment.category,
                        pages=segment.pages,
                    )
                )

        @step
        async def extract_scenes(self, ev: SegmentEvent, ctx: Context) -> StopEvent:
            ready = ctx.collect_events(ev, [SegmentEvent] * await ctx.store.get("segments_count"))
            if ready is None:
                return None

            extracted_scenes: List[dict] = []
            movie_title = ""
            source_file = ""
            file_id = ""

            for segment_event in ready:
                movie_title = segment_event.movie_title
                source_file = segment_event.source_file
                file_id = segment_event.file_id
                if segment_event.category != "scene_content":
                    continue
                if not segment_event.pages:
                    continue
                page_range = f"{min(segment_event.pages)}-{max(segment_event.pages)}"
                result = await self.client.extraction.extract(
                    file_id=file_id,
                    config={
                        "extraction_mode": "PREMIUM",
                        "use_reasoning": False,
                        "cite_sources": False,
                        "confidence_scores": True,
                        "page_range": page_range,
                    },
                    data_schema=SceneSchema.model_json_schema(),
                )
                if result and result.data:
                    extracted_scenes.append(result.data)

            # Normalize and trim to a top-N scene set for prompting.
            normalized = []
            for idx, item in enumerate(extracted_scenes[:top_scenes_per_movie], start=1):
                scene = SceneSchema.model_validate(item)
                normalized.append(
                    {
                        "scene_id": f"scene_{idx:02d}",
                        **scene.model_dump(),
                    }
                )

            payload = MovieParseOutput(
                movie_title=movie_title,
                source_file=source_file,
                scenes=[SceneSchema.model_validate(scene) for scene in normalized],
            )
            return StopEvent(result=payload.model_dump())

    outputs = []
    for script_file in script_files:
        workflow = ScriptWorkflow(timeout=1200, verbose=False)
        result = await workflow.run(start_event=StartEvent(file_path=str(script_file)))
        # result may already be dict-like depending on workflow runtime return semantics.
        payload = dict(result) if isinstance(result, dict) else result
        if not payload:
            continue
        movie_key = script_file.stem.lower()
        out_file = output_path / f"{movie_key}.llama_iconic_scenes.json"
        with open(out_file, "w", encoding="utf-8") as handle:
            import json

            json.dump(payload, handle, indent=2, ensure_ascii=True)
        outputs.append(str(out_file))

    return {"processed": len(outputs), "outputs": outputs}
