---
name: movie-scene-finder
description: Parse movie script .txt files to identify and extract the most iconic and well-known scenes. Use this skill whenever the user uploads movie scripts, screenplays, or .txt files containing film dialogue/action and wants to find famous scenes, iconic moments, quotable lines, or memorable sequences. Also trigger when the user mentions "famous scenes", "iconic moments", "best scenes", "well-known clips", or wants to analyze screenplays for cultural significance. Works with any well-known movie script in .txt format.
---

# Movie Scene Finder

A skill for parsing movie script .txt files and identifying the most iconic, culturally significant scenes.

## Overview

This skill processes movie screenplay .txt files, identifies the film, and extracts the most well-known scenes ranked by cultural impact. It handles standard screenplay formatting (scene headings, character names, dialogue, action lines) as well as informal transcript-style scripts.

---

## Step 1: Read Uploaded Scripts

```bash
ls /mnt/user-data/uploads/*.txt
```

Read each `.txt` file and identify the movie title. Scripts may contain the title in a header, or you can infer it from character names, dialogue, and plot elements.

For each file, note:
- **Filename** and detected **movie title**
- **Format type**: standard screenplay (with `INT.`/`EXT.` scene headings, character cues in CAPS) vs. transcript/informal format
- **Approximate length** (line count)

---

## Step 2: Parse Script Structure

### Standard Screenplay Format
Scripts typically follow this structure:
- **Scene headings** (sluglines): Lines starting with `INT.` or `EXT.` (interior/exterior)
- **Action/description**: Prose paragraphs describing what's happening on screen
- **Character cues**: Character name in ALL CAPS on its own line, followed by dialogue
- **Parentheticals**: `(quietly)`, `(to John)` — acting directions within dialogue
- **Transitions**: `CUT TO:`, `FADE IN:`, `DISSOLVE TO:`

### Parsing Strategy
1. **Split the script into scenes** using scene headings (`INT.`/`EXT.`) or major transitions as delimiters
2. If no standard headings exist (transcript format), split on large gaps, location changes mentioned in description, or `---`/`***` dividers
3. For each scene, extract:
   - Scene heading / location
   - Characters present (names appearing in CAPS before dialogue)
   - All dialogue lines with speaker attribution
   - Key action/description lines
   - Approximate position in the script (beginning / middle / end) as a percentage

---

## Step 3: Identify the Movie & Its Famous Scenes

This is the core intelligence step. Use your knowledge of cinema to identify which scenes are the most iconic.

### Identification Signals
For each parsed scene, check against these markers of iconic status:

1. **Quotable dialogue**: Lines that have entered popular culture. Look for dialogue that matches famous quotes you know from the film. Examples:
   - "Here's looking at you, kid" → *Casablanca*
   - "I'm going to make him an offer he can't refuse" → *The Godfather*
   - "You can't handle the truth!" → *A Few Good Men*

2. **Pivotal plot moments**: Scenes where major reveals, twists, or climactic confrontations occur:
   - The shower scene → *Psycho*
   - "I am your father" → *The Empire Strikes Back*
   - The ending twist → *The Sixth Sense*

3. **Culturally referenced sequences**: Scenes widely parodied, homaged, or referenced in other media:
   - The bullet-dodge → *The Matrix*
   - The chest-burster → *Alien*
   - The "Tiny Dancer" bus scene → *Almost Famous*

4. **Award-recognized moments**: Scenes frequently cited in "best of" lists, Oscar highlight reels, or AFI rankings

5. **Character-defining moments**: Scenes that crystallize a character's arc or deliver their most memorable performance

### Ranking Criteria
Score each candidate scene on a **1–10 scale** across these dimensions:

| Dimension | Description |
|-----------|-------------|
| **Cultural Penetration** | How widely known is this scene outside of film enthusiasts? Would a casual viewer recognize it? |
| **Quotability** | Does it contain lines people actually quote in everyday life? |
| **Emotional Impact** | How powerful is the scene's dramatic, comedic, or visceral effect? |
| **Visual Iconography** | Is there a specific image or shot from this scene that's become iconic? |
| **Narrative Significance** | How critical is this scene to the film's story and themes? |

**Composite score** = average of all five dimensions.

---

## Step 4: Extract and Present Results

For each movie, produce a structured output with the **top 5 most iconic scenes**, ranked by composite score.

### Output Format

For each movie, create an entry with:

```
## [Movie Title] (Year)
### Scene Rank #N: "[Scene Name / Nickname]"
- **Location in script**: Page/line range or percentage through script
- **Setting**: INT./EXT. location from scene heading
- **Characters**: Who appears in the scene
- **Famous lines**: The most quoted dialogue from the scene (cite exact lines from the script)
- **What happens**: 2-3 sentence summary of the scene's action
- **Why it's iconic**: Brief explanation of cultural significance
- **Composite Score**: X.X/10
  - Cultural Penetration: X/10
  - Quotability: X/10
  - Emotional Impact: X/10
  - Visual Iconography: X/10
  - Narrative Significance: X/10
```

### Extraction Rules
- **Quote exactly** from the script file — do not paraphrase the dialogue. These are the user's own uploaded files, not copyrighted web sources.
- Include **5-15 lines of surrounding context** (dialogue + action) for each famous scene so the user gets the full moment.
- If a scene spans many pages, extract the **core moment** (the most famous 20-40 lines) rather than the entire scene.
- Preserve original formatting (character names in caps, parentheticals, action lines).

---

## Step 5: Generate Output File

### Primary output: Markdown report
Create a comprehensive `.md` file saved to `/mnt/user-data/outputs/` with:

1. **Summary table**: All movies × top scenes in a quick-reference grid
2. **Detailed scene breakdowns**: Full extracted scenes with analysis (per Step 4 format)
3. **Cross-movie highlights**: "Top 10 Most Iconic Moments Across All Scripts" ranked list
4. **Quotable lines collection**: A compiled list of the most famous individual lines across all scripts

### Optional secondary outputs (if user requests):
- **Individual scene excerpts** as separate `.txt` files (one per iconic scene)
- **CSV/spreadsheet** of all scenes with scores for sorting and filtering

---

## Edge Cases & Troubleshooting

### Script format variations
- **No scene headings**: Split on blank-line clusters (3+ blank lines), location mentions in description, or TIME indicators
- **All-caps scripts**: Some older scripts are entirely uppercase — parse character names by indentation or colon delimiters instead
- **Numbered scenes**: Some shooting scripts have scene numbers — use these as primary delimiters
- **Multiple scripts for same movie**: If drafts differ, note which draft and flag dialogue differences in famous scenes

### Movie not recognized
If you cannot confidently identify the movie from the script contents:
1. Search for distinctive character names + dialogue combinations
2. Ask the user to confirm the movie title
3. If the movie is obscure, note that "iconic scene" identification relies more on narrative analysis than cultural knowledge, and adjust scoring to weight Narrative Significance and Emotional Impact more heavily

### Very long scripts
For scripts over 15,000 lines:
- Do a first pass scanning only for dialogue lines matching known famous quotes
- Then expand to full scene extraction around those anchor points
- Finally scan remaining scenes for pivotal plot moments

---

## Example Workflow

```
User uploads: godfather.txt, matrix.txt, pulp_fiction.txt

1. Read & identify each file
2. Parse into scenes:
   - godfather.txt → 87 scenes detected
   - matrix.txt → 63 scenes detected  
   - pulp_fiction.txt → 45 scenes detected (non-linear structure)
3. For each movie, score scenes against cultural knowledge
4. Extract top 5 per movie with full dialogue and analysis
5. Generate ranked cross-movie summary
6. Save report to /mnt/user-data/outputs/iconic-scenes-report.md
```

---

## Important Notes

- Always read the actual script text — do not rely solely on your knowledge of the movie. The script may be a specific draft that differs from the final film.
- Scenes in the script may not match the final cut exactly. Note any significant differences you spot between the script text and the commonly known version of the scene.
- For non-English scripts or scripts with non-English dialogue sections, preserve the original language and provide translations in parentheses.
- When presenting results, use the `present_files` tool to share the final report with the user.