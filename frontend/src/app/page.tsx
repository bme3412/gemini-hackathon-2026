"use client";

import { useState, useEffect, useRef } from "react";
import Image from "next/image";

interface SceneOption {
  option_id: string;
  scene_id_a: string;
  scene_id_b: string;
  title: string;
  pitch: string;
  pivot_point: string;
  slugline_a: string;
  slugline_b: string;
  tone: string;
}

interface RemixResponse {
  script_remix: string;
  video_prompt: string;
  video_url?: string;
  video_job_id?: string;
  concept_art_url?: string;
  video_error?: string;
  transition_scene_a?: string;
  target_scene_b?: string;
  pivot_point?: string;
  visual_transition_advice?: string;
  grounding_details?: string[];
  selected_scene_a?: string;
  selected_scene_b?: string;
}

function TvFrame({ children, label }: { children: React.ReactNode; label?: string }) {
  return (
    <div className="tv-frame">
      <div className="tv-screen tv-flicker">{children}</div>
      <div className="tv-controls">
        <div className="tv-knob" />
        <span className="tv-label">{label || "Veo 3.1"}</span>
        <div className="tv-knob" />
      </div>
    </div>
  );
}

interface DemoCache {
  movie_a: string;
  movie_b: string;
  scene_options: SceneOption[];
  cached_result: RemixResponse & { selected_option_id: string };
}

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function Home() {
  const [scripts, setScripts] = useState<string[]>([]);
  const [movieA, setMovieA] = useState("");
  const [movieB, setMovieB] = useState("");
  const [instruction, setInstruction] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<RemixResponse | null>(null);
  const [videoElapsed, setVideoElapsed] = useState(0);
  const [sceneOptions, setSceneOptions] = useState<SceneOption[]>([]);
  const [selectedOption, setSelectedOption] = useState<SceneOption | null>(null);
  const [loadingOptions, setLoadingOptions] = useState(false);
  const elapsedRef = useRef(0);
  const activeJobRef = useRef<string | null>(null);
  const demoCacheRef = useRef<DemoCache | null>(null);

  // Load demo cache on mount
  useEffect(() => {
    fetch("/demo-cache.json").then(r => r.json()).then((d: DemoCache) => { demoCacheRef.current = d; }).catch(() => {});
  }, []);

  const isDemoPair = (a: string, b: string) => {
    const dc = demoCacheRef.current;
    if (!dc) return false;
    return (a === dc.movie_a && b === dc.movie_b) || (a === dc.movie_b && b === dc.movie_a);
  };

  useEffect(() => {
    if (result && result.video_job_id && !result.video_url && !result.video_error) {
      if (activeJobRef.current !== result.video_job_id) {
        elapsedRef.current = 0;
        activeJobRef.current = result.video_job_id;
        setVideoElapsed(0);
      }
      const tickId = setInterval(() => {
        elapsedRef.current += 1;
        setVideoElapsed(elapsedRef.current);
      }, 1000);
      return () => clearInterval(tickId);
    } else {
      activeJobRef.current = null;
      elapsedRef.current = 0;
      setVideoElapsed(0);
    }
  }, [result?.video_job_id, result?.video_url]);

  useEffect(() => {
    if (!result?.video_job_id || result?.video_url || result?.video_error) return;
    const jobId = result.video_job_id;
    let cancelled = false;
    const poll = async () => {
      try {
        const res = await fetch(`${API}/video-status/${jobId}`);
        if (res.ok && !cancelled) {
          const data = await res.json();
          if (data.status === "done") setResult((p) => p ? { ...p, video_url: data.video_url } : p);
          else if (data.status === "error") setResult((p) => p ? { ...p, video_error: "Video was filtered by safety checks. Try a different transition." } : p);
        }
      } catch (e) { console.error("Poll error:", e); }
    };
    poll();
    const id = setInterval(poll, 4000);
    return () => { cancelled = true; clearInterval(id); };
  }, [result?.video_job_id, result?.video_url, result?.video_error]);

  useEffect(() => {
    fetch(`${API}/scripts`).then(r => r.json()).then(d => { if (Array.isArray(d)) setScripts(d); }).catch(() => {
      const fallback = ["Forrest Gump", "The Matrix", "Good Will Hunting", "Jurassic Park",
        "Fight Club", "The Godfather", "The Shawshank Redemption", "Inception",
        "The Truman Show", "Pulp Fiction"];
      setScripts(fallback);
    });
  }, []);

  useEffect(() => {
    if (!movieA || !movieB) { setSceneOptions([]); setSelectedOption(null); setInstruction(""); return; }
    if (isDemoPair(movieA, movieB)) {
      const dc = demoCacheRef.current!;
      setSceneOptions(dc.scene_options);
      setSelectedOption(null);
      setInstruction("");
      setResult(null);
      return;
    }
    const go = async () => {
      setLoadingOptions(true); setSceneOptions([]); setSelectedOption(null); setInstruction(""); setResult(null);
      try {
        const res = await fetch(`${API}/scene-options`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ movie_a: movieA, movie_b: movieB }) });
        const data = await res.json();
        if (data.options && Array.isArray(data.options)) setSceneOptions(data.options);
      } catch (e) { console.error(e); }
      finally { setLoadingOptions(false); }
    };
    go();
  }, [movieA, movieB]);

  const handleSelectOption = (opt: SceneOption) => { setSelectedOption(opt); setInstruction(opt.pitch); };

  const handleRemix = async () => {
    if (!movieA || !movieB || !instruction) return;

    // Check for cached demo result
    const dc = demoCacheRef.current;
    if (dc && isDemoPair(movieA, movieB) && selectedOption?.option_id === dc.cached_result.selected_option_id) {
      setLoading(true); setResult(null);
      // Brief artificial delay for realism
      await new Promise(r => setTimeout(r, 2500));
      setResult(dc.cached_result);
      setLoading(false);
      return;
    }

    setLoading(true); setResult(null);
    try {
      const body: Record<string, string> = { movie_a: movieA, movie_b: movieB, instruction };
      if (selectedOption) { body.scene_id_a = selectedOption.scene_id_a; body.scene_id_b = selectedOption.scene_id_b; }
      const res = await fetch(`${API}/remix`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      setResult(await res.json());
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  };

  return (
    <div className="min-h-screen">
      {/* Header */}
      <header className="relative pt-20 pb-12 text-center px-6">
        <div className="absolute inset-0 bg-gradient-to-b from-[var(--gold)]/[0.03] via-transparent to-transparent pointer-events-none" />
        <h1 className="display text-5xl md:text-7xl font-extrabold tracking-tight mb-4 bg-gradient-to-r from-[var(--gold)] via-[var(--fg)] to-[var(--gold)] bg-clip-text text-transparent">
          Cinematic Alchemy
        </h1>
        <p className="text-[var(--fg-dim)] text-base md:text-lg italic max-w-lg mx-auto leading-relaxed">
          What if the greatest movies never ended — they collided
        </p>
      </header>

      <main className="max-w-6xl mx-auto px-6 pb-20">
        <div className="grid grid-cols-1 lg:grid-cols-[320px_1fr] gap-10">

          {/* Sidebar */}
          <aside className="space-y-6">
            <div className="card-up rounded-2xl p-6 space-y-5">
              <h2 className="display text-base font-extrabold uppercase tracking-[0.2em] text-[var(--gold)]">
                The Lab
              </h2>
              <label className="block space-y-1">
                <span className="mono text-[10px] uppercase tracking-widest text-[var(--fg-dim)]">Primary Reality</span>
                <select value={movieA} onChange={e => setMovieA(e.target.value)}
                  className="w-full bg-[var(--surface)] border border-[var(--border-hi)] rounded-lg py-2.5 px-3 text-sm text-[var(--fg)] outline-none focus:border-[var(--gold)]/40 transition-colors">
                  <option value="">Select a film...</option>
                  {scripts.map(s => <option key={s} value={s}>{s}</option>)}
                </select>
              </label>
              <label className="block space-y-1">
                <span className="mono text-[10px] uppercase tracking-widest text-[var(--fg-dim)]">Merge Reality</span>
                <select value={movieB} onChange={e => setMovieB(e.target.value)}
                  className="w-full bg-[var(--surface)] border border-[var(--border-hi)] rounded-lg py-2.5 px-3 text-sm text-[var(--fg)] outline-none focus:border-[var(--gold)]/40 transition-colors">
                  <option value="">Select a film...</option>
                  {scripts.map(s => <option key={s} value={s}>{s}</option>)}
                </select>
              </label>
              <label className="block space-y-1">
                <span className="mono text-[10px] uppercase tracking-widest text-[var(--fg-dim)]">
                  Transition Instruction {loadingOptions && <span className="text-[var(--gold)] animate-pulse ml-1">finding...</span>}
                </span>
                <textarea value={instruction} onChange={e => setInstruction(e.target.value)}
                  placeholder={loadingOptions ? "Discovering transitions..." : "Select a transition or write your own"}
                  className="w-full bg-[var(--surface)] border border-[var(--border-hi)] rounded-lg py-3 px-3 h-28 text-sm text-[var(--fg)] outline-none resize-none focus:border-[var(--gold)]/40 transition-colors leading-relaxed" />
              </label>
              <button onClick={handleRemix} disabled={loading || !instruction}
                className="display w-full bg-[var(--gold)] hover:bg-[var(--gold-dim)] text-black font-extrabold py-3.5 rounded-lg uppercase tracking-[0.15em] text-sm transition-all hover:scale-[1.02] active:scale-[0.98] disabled:opacity-30 disabled:pointer-events-none glow-btn">
                {loading ? "Forging..." : "Forge Sequence"}
              </button>
            </div>
          </aside>

          {/* Main content */}
          <div className="space-y-8 min-w-0">

            {/* Empty */}
            {!movieA && !movieB && !loading && !result && (
              <TvFrame label="Awaiting Signal">
                <div className="aspect-video bg-black/80 flex flex-col items-center justify-center gap-3 p-8">
                  <p className="text-[var(--fg-dim)] text-sm text-center">Select two films to begin</p>
                </div>
              </TvFrame>
            )}

            {/* Loading options */}
            {loadingOptions && (
              <div className="flex flex-col items-center justify-center py-20 space-y-5">
                <div className="w-10 h-10 border-2 border-[var(--gold)] border-t-transparent rounded-full animate-spin" />
                <p className="mono text-[var(--gold)] text-xs tracking-[0.25em] uppercase animate-pulse">Discovering transitions...</p>
              </div>
            )}

            {/* Option cards */}
            {sceneOptions.length > 0 && !loading && !result && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {sceneOptions.map(opt => {
                  const sel = selectedOption?.option_id === opt.option_id;
                  return (
                    <button key={opt.option_id} onClick={() => handleSelectOption(opt)}
                      className={`text-left rounded-xl p-5 transition-all duration-200 hover:scale-[1.01] ${
                        sel ? "card-up ring-1 ring-[var(--gold)]/60 shadow-lg shadow-[var(--gold)]/5" : "card hover:border-[var(--border-hi)]"
                      }`}>
                      <h4 className="display text-[15px] font-bold text-[var(--fg)] mb-1 leading-snug">{opt.title}</h4>
                      <p className="text-[13px] text-[var(--fg-dim)] leading-relaxed">{opt.pitch}</p>
                    </button>
                  );
                })}
              </div>
            )}

            {/* Forging */}
            {loading && (
              <div className="flex flex-col items-center justify-center py-20 space-y-5">
                <div className="w-14 h-14 border-2 border-[var(--gold)] border-t-transparent rounded-full animate-spin" />
                <p className="display text-[var(--gold)] font-bold tracking-[0.2em] uppercase text-sm animate-pulse">Forging Sequence...</p>
              </div>
            )}

            {/* Result */}
            {result && (
              <div className="space-y-6">
                <button onClick={() => setResult(null)}
                  className="mono text-[10px] uppercase tracking-[0.2em] text-[var(--fg-dim)] hover:text-[var(--gold)] transition-colors">
                  &larr; Back to options
                </button>

                {/* Context banner */}
                {selectedOption && (
                  <div className="card-up rounded-xl overflow-hidden p-5">
                    <div className="flex items-baseline gap-2 mb-3">
                      <span className="display text-base font-extrabold text-[var(--fg)]">{movieA}</span>
                      <span className="text-[var(--gold)] text-sm">&times;</span>
                      <span className="display text-base font-extrabold text-[var(--fg)]">{movieB}</span>
                    </div>
                    <p className="display text-sm font-bold text-[var(--gold)] mb-3">{selectedOption.title}</p>
                    <div className="grid grid-cols-1 md:grid-cols-[1fr_32px_1fr] gap-3 items-start">
                      <div className="space-y-1">
                        <span className="mono text-[9px] uppercase tracking-widest text-[var(--fg-dim)]">Scene A</span>
                        {result.transition_scene_a && <p className="text-xs text-[var(--fg-dim)] leading-relaxed">{result.transition_scene_a}</p>}
                      </div>
                      <div className="hidden md:flex items-center justify-center self-center">
                        <span className="text-[var(--gold)]/30 text-xs">&harr;</span>
                      </div>
                      <div className="space-y-1">
                        <span className="mono text-[9px] uppercase tracking-widest text-[var(--fg-dim)]">Scene B</span>
                        {result.target_scene_b && <p className="text-xs text-[var(--fg-dim)] leading-relaxed">{result.target_scene_b}</p>}
                      </div>
                    </div>
                  </div>
                )}

                {/* Video */}
                <TvFrame label={result.video_url ? "Playback" : result.video_error ? "No Signal" : "Generating"}>
                  {result.video_url ? (
                    <div className="relative aspect-video bg-black">
                      <video src={result.video_url} controls autoPlay loop className="w-full h-full object-cover" />
                    </div>
                  ) : result.video_error ? (
                    <div className="relative aspect-video bg-black flex flex-col items-center justify-center space-y-3 p-8">
                      {result.concept_art_url && <Image src={result.concept_art_url} alt="" fill className="object-cover opacity-10" />}
                      <div className="relative z-10 text-center space-y-3">
                        <p className="text-red-400/80 mono text-xs tracking-widest uppercase">{result.video_error}</p>
                        <button onClick={() => setResult(null)} className="text-xs text-[var(--gold)] hover:underline">Try a different option</button>
                      </div>
                    </div>
                  ) : result.concept_art_url ? (
                    <div className="relative aspect-video bg-black">
                      <Image src={result.concept_art_url} alt="" fill className="object-cover opacity-40" />
                      <div className="absolute inset-0 flex flex-col items-center justify-center space-y-3 bg-black/40 z-10">
                        <div className="w-8 h-8 border-2 border-[var(--gold)] border-t-transparent rounded-full animate-spin" />
                        <p className="mono text-[var(--gold)] text-xs tracking-widest uppercase animate-pulse">Animating...</p>
                        <p className="mono text-[var(--fg-dim)] text-[11px] tabular-nums">{videoElapsed}s &middot; typically 30-90s</p>
                      </div>
                    </div>
                  ) : result.video_job_id ? (
                    <div className="aspect-video bg-black flex flex-col items-center justify-center space-y-3">
                      <div className="w-8 h-8 border-2 border-[var(--gold)] border-t-transparent rounded-full animate-spin" />
                      <p className="mono text-[var(--gold)] text-xs tracking-widest uppercase animate-pulse">Forging...</p>
                      <p className="mono text-[var(--fg-dim)] text-[11px] tabular-nums">{videoElapsed}s &middot; typically 30-90s</p>
                    </div>
                  ) : <div className="aspect-video bg-black" />}
                </TvFrame>

                {/* Grounding */}
                {result.grounding_details && result.grounding_details.length > 0 && (
                  <div className="card rounded-xl p-5">
                    <h3 className="display text-[11px] font-bold uppercase tracking-[0.2em] text-[var(--fg-dim)] mb-3 pb-2 border-b border-[var(--border)]">Cinematic Grounding</h3>
                    <ul className="space-y-1.5">
                      {result.grounding_details.map((d, i) => (
                        <li key={i} className="text-xs text-[var(--fg-dim)] leading-relaxed flex gap-2">
                          <span className="text-[var(--gold)]/30 flex-shrink-0">&#9656;</span>{d}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Script */}
                <div className="card-up rounded-xl p-6 relative overflow-hidden">
                  <div className="absolute top-2 right-4 display text-7xl font-extrabold uppercase text-[var(--gold)]/[0.03] pointer-events-none select-none">Script</div>
                  <h3 className="display text-[11px] font-bold uppercase tracking-[0.2em] text-[var(--fg-dim)] mb-5 pb-2 border-b border-[var(--border)]">The Continuous Sequence</h3>
                  <div className="mono text-[13px] leading-[1.8] whitespace-pre-wrap max-h-[60vh] overflow-y-auto pr-3 text-[var(--fg)]/90">
                    {result.script_remix}
                  </div>
                </div>

                {/* Prompt */}
                <details className="card rounded-xl">
                  <summary className="mono px-5 py-3 cursor-pointer text-[9px] uppercase tracking-[0.2em] text-[var(--fg-dim)]/40 hover:text-[var(--fg-dim)] transition-colors">
                    Prompt Strategy
                  </summary>
                  <p className="mono px-5 pb-4 text-[11px] text-[var(--fg-dim)]/50 leading-relaxed">{result.video_prompt}</p>
                </details>
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
