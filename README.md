# What if the greatest movies never ended — they collided?

I used the scripts from the top movies of all time on IMDB, parsed out the best scenes, then converted into video gen prompts. Enjoy.

---

**Cinematic Alchemy** uses Google's Gemini API to find the invisible seams between iconic films and forge continuous scene transitions — generating original video with Veo 3.1 that bridges two movies through a shared sensory moment.

Select two films. The AI reads both screenplays, identifies a shared sensory moment, and generates a single continuous shot where one world flows into the other.

---

## How it works

```
┌──────────────┐     ┌──────────────┐
│  Screenplay  │     │  Screenplay  │
│   Film A     │     │   Film B     │
└──────┬───────┘     └──────┬───────┘
       │                    │
       ▼                    ▼
┌──────────────────────────────────┐
│   Gemini 2.5 Flash               │
│   Scene Extraction & Ranking     │
│   (iconic moments, props,        │
│    visual atmosphere, hooks)     │
└──────────────┬───────────────────┘
               │
               ▼
┌──────────────────────────────────┐
│   Transition Discovery           │
│   3-4 options ranked by          │
│   sensory bridge strength        │
└──────────────┬───────────────────┘
               │  user picks one
               ▼
┌──────────────────────────────────┐
│   Gemini 2.5 Pro                 │
│   Seam Construction              │
│   - screenplay-format remix      │
│   - video prompt (sanitized)     │
│   - transition choreography      │
└──────────────┬───────────────────┘
               │
               ▼
┌──────────────────────────────────┐
│   Keyframes (Gemini image model) │
│   opening frame in Film A        │
│   closing frame in Film B        │
└──────────────┬───────────────────┘
               │
               ▼
┌──────────────────────────────────┐
│   Veo 3.1 Fast Generate          │
│   first/last-frame interpolation │
│   + safety-filter auto-retry     │
│   → 8s continuous video          │
└──────────────────────────────────┘
```

### Pipeline detail

1. **Scene Extraction** — Pre-parsed iconic scene JSONs (or live Gemini extraction from full screenplays) identify 2-3 top scenes per film with action beats, props/motifs, dialogue, visual atmosphere, and *transition hooks* — specific sensory details that can bridge into another world.

2. **Transition Discovery** — Gemini analyzes both scene sets and proposes 3-4 ranked transition options. Each option identifies a *pivot point*: the shared detail that lets one scene flow into another.

3. **Seam Construction** — Once the user selects a transition, Gemini writes a full screenplay-format remix and a detailed video generation prompt. The prompt emphasizes hyper-specific visual descriptors (exact clothing, props, settings, lighting) rather than character names — keeping the output recognizable while avoiding content filters.

4. **Video Generation** — Gemini writes two still-frame prompts: an opening frame inside Film A and a closing frame inside Film B, composed so the pivot element sits at the same screen position in both. The image model renders them, and Veo 3.1 interpolates between the two frames, so both ends of the clip are anchored. If a keyframe fails, the pipeline falls back to prompt-only generation (with reference images when available). A three-layer safety system handles content filtering:
   - Prompt engineering with visual specificity over names
   - Gemini Flash sanitization pass (rewrites to "cinematically anonymous" language)
   - Automatic retry with aggressive abstraction if the first attempt is filtered

5. **Reference Images** (`VIDEO_MODE=reference`, and the fallback path) — Google Search grounding fetches iconic stills for each film. These are stored as typed assets (primary character, secondary character, hero prop/setting) and passed to Veo as visual anchors. Veo does not combine reference images with first/last frames.

---

## Stack

| Layer | Technology |
|-------|-----------|
| **Video generation** | Veo 3.1 Fast Generate (Google Gemini API) |
| **Scene analysis** | Gemini 2.5 Flash / Pro with structured output |
| **Reference images** | Gemini + Google Search grounding |
| **Script parsing** | Pre-extracted iconic scene JSONs + optional LlamaIndex pipeline |
| **Backend** | FastAPI (Python) |
| **Frontend** | Next.js 16, React 19, Tailwind CSS 4 |
| **Deployment** | Vercel (frontend) |

---

## Quickstart

### Prerequisites

- Python 3.10+
- Node.js 18+
- A [Gemini API key](https://aistudio.google.com/apikey) with Veo access

### Setup

```bash
# Clone
git clone https://github.com/bme3412/gemini-hackathon-2026.git
cd gemini-hackathon-2026

# Environment
echo 'GEMINI_API_KEY=your_key_here' > .env

# Backend
cd backend
pip install -r requirements.txt
python main.py
# → http://localhost:8000

# Frontend (new terminal)
cd frontend
npm install
npm run dev
# → http://localhost:3000
```

---

## Project structure

```
├── backend/
│   ├── main.py                    # FastAPI server + endpoints
│   ├── remix_engine.py            # Core AI pipeline (scene extraction,
│   │                              #   transition discovery, seam construction,
│   │                              #   video generation, safety handling)
│   ├── fetch_reference_images.py  # Google Search grounding → image download
│   ├── llama_script_agent.py      # Optional LlamaIndex script parsing
│   ├── requirements.txt
│   └── scripts_library/
│       ├── *.txt                  # Full screenplays (10 films)
│       ├── iconic_scenes_json/    # Pre-extracted scene data per film
│       └── reference_images/      # Fetched stills (character, prop, setting)
│
├── frontend/
│   ├── src/app/
│   │   ├── page.tsx               # Main UI (selection, options, video player)
│   │   ├── layout.tsx             # Fonts + metadata
│   │   └── globals.css            # Hollywood gold theme + TV frame styles
│   └── public/
│
└── criteria/                      # Hackathon problem statements + judging
```

---

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/scripts` | List available film titles |
| `POST` | `/scene-options` | Generate 3-4 transition options for a film pair |
| `POST` | `/remix` | Construct the seam: screenplay remix + video generation |
| `GET` | `/video-status/{id}` | Poll video generation progress |
| `POST` | `/suggest-mashup` | Generate a single mashup suggestion |
| `POST` | `/fetch-reference-images` | Fetch reference images via Google Search |
| `POST` | `/parse-scripts-llama` | Optional LlamaIndex script parsing |

---

## Film library

The app ships with 10 screenplays, each with pre-extracted iconic scenes:

Forrest Gump · The Matrix · Good Will Hunting · Jurassic Park · Fight Club · The Godfather · The Shawshank Redemption · Inception · The Truman Show · Pulp Fiction

Any pair can be combined. The system finds the strongest sensory bridges between their most recognizable moments.

---

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `GEMINI_API_KEY` | *required* | Google Gemini API key |
| `VIDEO_MODEL` | `veo-3.1-fast-generate-preview` | Veo model identifier |
| `VIDEO_MODE` | `interpolation` | `interpolation` (first/last keyframes) or `reference` (prompt + reference images) |
| `IMAGE_MODEL` | `gemini-2.5-flash-image` | Model used to render keyframes |
| `VIDEO_DURATION_SECONDS` | `4` | Generated clip length (8s with keyframes or reference images) |
| `VIDEO_ASPECT_RATIO` | `16:9` | Output aspect ratio |
| `VIDEO_RESOLUTION` | `720p` | Output resolution |
| `USE_REFERENCE_IMAGES` | `true` | Pass fetched stills to Veo when not interpolating |
| `USE_CONCEPT_ART` | `false` | Generate concept art before video |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Backend URL for frontend |

---

## Hackathon context

Built for the **Gemini and Film** track:

> *Leverage Gemini to create non-linear narratives and AI-native production tools that redefine the boundary between creator and audience.*

Cinematic Alchemy treats every film ever made as raw material for new stories. The audience becomes the editor — choosing which worlds collide and watching the AI find the invisible thread between them.

---

## License

MIT
