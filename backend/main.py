from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import os
from pydantic import BaseModel
from typing import List, Optional
from remix_engine import RemixEngine
from llama_script_agent import parse_scripts_with_llama, LlamaIntegrationUnavailable

app = FastAPI()

# Auto-load environment variables for local runs (python main.py).
def load_env_file():
    candidates = [
        os.path.join("..", ".env"),  # project root when cwd=backend
        os.path.join(".env"),        # backend-local fallback
        os.path.join(os.path.dirname(__file__), "..", ".env"),  # absolute root path fallback
    ]

    for env_path in candidates:
        normalized = os.path.abspath(env_path)
        if not os.path.exists(normalized):
            continue
        with open(normalized, "r", encoding="utf-8") as env_file:
            for raw_line in env_file:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
        break


load_env_file()

# Allow frontend to communicate with backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SCRIPTS_DIR = "scripts_library"

# Initialize Remix Engine
try:
    remix_engine = RemixEngine()
except ValueError as e:
    print(f"Warning: {e}. Remix functionality will be disabled until API key is set.")
    remix_engine = None

class RemixRequest(BaseModel):
    movie_a: str
    movie_b: str
    instruction: str
    scene_id_a: Optional[str] = None
    scene_id_b: Optional[str] = None

class SuggestRequest(BaseModel):
    movie_a: str
    movie_b: str

class SceneOptionsRequest(BaseModel):
    movie_a: str
    movie_b: str

class LlamaParseRequest(BaseModel):
    scripts_dir: str = "scripts_library"
    output_dir: str = "scripts_library/iconic_scenes_json"
    top_scenes_per_movie: int = 6

@app.get("/scripts")
async def list_scripts():
    if not os.path.exists(SCRIPTS_DIR):
        return []
    # Return pretty names for the UI
    return [f.replace(".txt", "").replace("_", " ") for f in os.listdir(SCRIPTS_DIR) if f.endswith(".txt")]

@app.post("/suggest-mashup")
async def suggest_mashup(request: SuggestRequest):
    if not remix_engine:
        raise HTTPException(status_code=500, detail="Remix Engine not initialized.")
    try:
        suggestion = await remix_engine.suggest_mashup_instruction(request.movie_a, request.movie_b)
        return {"suggestion": suggestion}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/scene-options")
async def scene_options(request: SceneOptionsRequest):
    if not remix_engine:
        raise HTTPException(status_code=500, detail="Remix Engine not initialized.")
    try:
        options = await remix_engine.generate_scene_options(request.movie_a, request.movie_b)
        return {"options": [o.model_dump() for o in options]}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/remix")
async def remix_movies(request: RemixRequest):
    if not remix_engine:
        raise HTTPException(status_code=500, detail="Remix Engine not initialized. Check API Key.")
    
    try:
        result = await remix_engine.find_seam(
            request.movie_a, request.movie_b, request.instruction,
            scene_id_a=request.scene_id_a, scene_id_b=request.scene_id_b,
        )
        return result
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/video-status/{operation_name:path}")
async def get_video_status(operation_name: str):
    if not remix_engine:
        raise HTTPException(status_code=500, detail="Remix Engine not initialized.")
    url = remix_engine.poll_video_job(operation_name)
    if url == "error":
        return {"status": "error"}
    elif url:
         return {"status": "done", "video_url": url}
    else:
         return {"status": "processing"}

@app.post("/fetch-reference-images")
async def fetch_reference_images(movie_key: str = None):
    """Fetch reference images for one or all movies using Gemini + Google Search."""
    if not remix_engine:
        raise HTTPException(status_code=500, detail="Remix Engine not initialized.")
    try:
        from fetch_reference_images import fetch_images_for_movie
        import os as _os

        ref_dir = remix_engine.reference_images_dir
        if movie_key:
            keys = [movie_key]
        else:
            keys = sorted([
                d for d in _os.listdir(ref_dir)
                if _os.path.isdir(_os.path.join(ref_dir, d))
            ])

        results = {}
        for key in keys:
            await fetch_images_for_movie(remix_engine.client, key)
            manifest_path = _os.path.join(ref_dir, key, "manifest.json")
            if _os.path.exists(manifest_path):
                import json as _json
                with open(manifest_path, "r") as f:
                    m = _json.load(f)
                statuses = {a["role"]: a.get("status", "unknown") for a in m.get("assets", [])}
                results[key] = statuses

        remix_engine.reference_manifest_index = remix_engine._load_reference_manifest_index()
        return {"results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/parse-scripts-llama")
async def parse_scripts_llama(request: LlamaParseRequest):
    """
    Optional script parsing pipeline via LlamaCloud/LlamaIndex workflow.
    """
    try:
        result = await parse_scripts_with_llama(
            scripts_dir=request.scripts_dir,
            output_dir=request.output_dir,
            top_scenes_per_movie=request.top_scenes_per_movie,
        )
        return result
    except LlamaIntegrationUnavailable as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
