import os
from google import genai
import time


class VideoAnalyst:
    def __init__(self, client):
        self.client = client

    async def analyze_style(self, movie_name: str):
        """
        Uses Gemini 2.0 Flash to analyze the visual and rhythmic style of a movie.
        In a production environment, this would process actual video snippets.
        """
        prompt = f"""
        Analyze the cinematic style of the movie: {movie_name}.
        Focus on:
        1. Lighting & Color Palette (e.g. 'high contrast, cold blues')
        2. Camera Movement (e.g. 'handheld, jittery' vs 'smooth dollies')
        3. Pacing & Rhythm (e.g. 'rapid-fire cuts' vs 'meditative long takes')
        
        Provide a concise 'Multimodal Witness Report' for this film.
        """
        
        response = await self.client.aio.models.generate_content(
            model="models/gemini-2.0-flash",
            contents=[prompt]
        )
        return response.text.strip()
