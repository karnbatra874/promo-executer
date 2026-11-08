# Microdrama Promo Extractor

A command-line tool that reads microdrama screenplays and finds the best **promo clips** in them: 20–60 second moments that open on a hook, end on a cliffhanger, and make sense to someone who has never seen the show.

It returns, for every promo: the episode and start/end timestamp of each segment (in order), the hook, the cliffhanger, a one-line rationale, a score, a rank, and quality-control flags. It does **not** edit video, add music or add text overlays.

> This README describes what the code actually does today (LLM backend: **Google Gemini**, not Anthropic). Known problems are listed honestly in [Known issues](#known-issues).

---

## How it works

```
episode .txt files
      │
      ▼
 1. Ingest        parse structured script -> Line objects (type, speaker, tone, real timestamps)
      │
      ▼
 2. Time mapping  use the script's Start/End timestamps; fall back to a word-count estimate
      │
      ▼
 3. Chunking      group lines into ≤5000-word chunks (10-line overlap)
      │
      ▼
 4. Pass 1        LLM finds "anchors": hook moments and cliffhanger moments
      │
      ▼
 5. Pass 2        LLM expands anchors into promos (one or more line-range segments,
      │           may stitch non-contiguous segments); code maps lines -> timestamps
      ▼
 6. Dedupe        drop promos that overlap >50% with an earlier one
      │
      ▼
 7. Rule QC       word budget, pacing, pronoun soup, false cliffhanger, talking head
      │
      ▼
 8. Judge + rank  LLM scores hook / context / cliffhanger (1–10); weighted 40/30/30; tiers
      │
      ▼
 9. Outputs       JSON, review CSV, silent-visual-hook CSV
```

### Why two passes plus a judge?
- **Pass 1** is cheap and only asks "where are the strongest moments?", which keeps the model focused.
- **Pass 2** turns those moments into concrete, cuttable line ranges. The LLM only chooses line numbers; **timestamps are computed by code** from the script, so the model cannot invent times.
- **The judge** is a separate call that scores each finished promo against the three criteria in the brief.
- **Rule-based QC** catches failure modes that an LLM reading text cannot see.

---

## Requirements

- Python 3.10+
- A Google Gemini API key (free tier works; the client throttles to 14 requests/minute)
- Dependencies (see `requirements.txt`): `google-genai`, `pydantic`, `pyyaml`, `python-dotenv`, `pytest`

## Setup

```bash
# 1. (optional) create a virtual environment
python -m venv .venv
.venv\Scripts\activate            # Windows
# source .venv/bin/activate       # macOS / Linux

# 2. install
pip install -r requirements.txt
#   or, to also get the `promo-tool` command:
pip install -e .

# 3. add your API key – create a file named .env in the project root:
#    GEMINI_API_KEY=your_key_here
#    PROMO_MODEL=gemini-3.5-flash-lite      # optional, overrides settings.yaml
```

> ⚠️ **Never share or commit `.env`.** It is in `.gitignore`, but it was inside the project zip. If a real key was in it, revoke it and create a new one.

## Usage

```bash
# Parse + time-map only. No API calls, no key needed. Always do this first.
python main.py run data/input --dry-run

# Cheap real test: only the first chunk
python main.py run data/input --max-chunks 1

# Full run over every episode in a folder
python main.py run data/input

# One file
python main.py run "data/input/episode-001-Episode 1671703.txt"

# Custom output folder / settings file
python main.py run data/input --out my_results --settings config/settings.yaml

# Fit the pacing calibration factor from measured promo runtimes
python main.py calibrate
```

On Windows you can also use `run.bat run data\input`. If you installed with `pip install -e .`, `promo-tool run data/input` works too.

### Tests
```bash
python -m pytest -q
```
19 tests exist. **5 currently fail** (see Known issues).

---

## Input format

One `.txt` file per episode, in this structure (this is what the parser expects):

```
EPISODE NUMBER: Episode 1
EPISODE LOGLINE: ...
CONTINUITY NOTES: ...

--- SCRIPT START ---

SCENE 01
Scene heading: INT. CATHEDRAL – DAY
Scene start: 00:00.00
Scene end: 02:18.00

**CAMERA:**
Start: (00:00.00) | End: (00:04.80)
Symmetrical framing on the heavy church doors...

**MATRIARCH (Cold, Commanding):**
Start: (00:11.30) | End: (00:13.10)
"You should turn around, Juliana."

--- SCRIPT END ---
```

- Each `**HEADER:**` block becomes one *line*. Headers are classified as `CAMERA`, `ACTION`, `SOUND FX`, or **dialogue** (anything else; text in brackets is the delivery tone).
- `Start/End` timestamps are read as real times (`MM:SS.SS`).
- Files are loaded in **filename order**, which is why they are named `episode-001-…`, `episode-002-…`.
- If a file has no `--- SCRIPT START ---` marker, a simple legacy parser is used (`Episode N` headers, optional `[MM:SS]` prefixes); times are then estimated from word count.

---

## Output files (`data/output/`)

| File | Contents |
|---|---|
| `promos_all.json` | Every promo after dedupe, in discovery order |
| `promos_ranked.json` | Same promos sorted by `total_score` (best first) |
| `review_queue.csv` | One row per promo, ranked, with blank `HUMAN_*` columns for an editor to fill in |
| `visual_hook_candidates.csv` | Short action lines that *might* be strong silent visual hooks no promo covered |

Each promo in the JSON has:

| Field | Meaning |
|---|---|
| `promo_id` | `P1`, `P2`, … |
| `segments[]` | Ordered list of `{episode, start_line, end_line, start_timestamp, end_timestamp, word_count}`; more than one entry means a stitched promo |
| `episodes_spanned` | Episodes the promo draws from |
| `hook`, `cliffhanger`, `rationale` | Short LLM-written descriptions |
| `scores` / `total_score` | `hook_velocity`, `context_independence`, `cliffhanger_friction` and their weighted total |
| `tier` | `Tier 1: Post Immediately`, `Tier 2: Post After Review`, `Tier 3: Low Priority`, or `Hold: fix QC errors` |
| `qc_flags[]` | Warnings/errors from the checks below |
| `est_duration_sec`, `word_count` | Total across all segments |

---

## Configuration

| File | What to change |
|---|---|
| `config/settings.yaml` | Model, chunk size, promo length limits, score weights, tier cut-offs, pause/keyword/pronoun regex lists |
| `config/characters.yaml` | Cast names and aliases for the pronoun-soup check (currently filled for the Juliana/Alexander show; **update it for each new show**) |
| `prompts/*.txt` | System prompt, Pass 1, Pass 2 and judge prompts |

Key defaults:

| Setting | Value |
|---|---|
| Promo length | 20–60 s (`min_seconds` / `max_seconds`) |
| Word budget | 50–150 words (`min_words` / `max_words`) – see Known issues |
| Ranking weights | hook 0.4, context independence 0.3, cliffhanger 0.3 |
| Tier 1 / Tier 2 cut-offs | ≥ 8.5 / ≥ 7.0 |
| Chunk size / overlap | 5000 words / 10 lines |
| Rate limit | 14 requests per minute, retries ×3, 60 s back-off on quota errors |

---

## Quality-control checks

| Check (`code`) | Severity | What it does | What still needs a human |
|---|---|---|---|
| `word_budget` | error if too long, warn if too short | Total words outside 50–150 | – |
| `pacing_too_long` / `pacing_too_short` | error / warn | Duration outside 20–60 s | Verify on footage |
| `pronoun_soup` | warn | First lines open with he/she/you… and name nobody from the cast list | Choose the fix (caption, earlier start) |
| `verify_cliffhanger_in_footage` | warn | Last line is an action/cut line (walks away, closes door…) | Confirm the beat really lands |
| `talking_head` | warn | Under 15 % action/camera lines | Look for a more visual alternative |
| `context_gap` | warn | The judge listed things a new viewer would not understand | Add context or pick a different start |
| *silent visual hook* (separate CSV) | – | Lists uncovered short action lines containing drama keywords | Watch the footage |

Any `error` flag puts the promo in the **Hold** tier regardless of score.

---

## Project structure

```
promo-extractor/
├── main.py / run.py / run.bat      entry points (main.py adds src/ to the path)
├── pyproject.toml, requirements.txt
├── config/        settings.yaml, characters.yaml
├── prompts/       system_promo_producer.txt, pass1_anchors.txt, pass2_segments.txt, judge.txt
├── src/promo_tool/
│   ├── cli.py            `run` and `calibrate` commands
│   ├── pipeline.py       orchestration, dedupe, CSV/JSON writers
│   ├── ingest.py         structured + legacy parsers, chunking
│   ├── timemap.py        timestamp parsing/formatting, word-count timing, calibration fit
│   ├── pass1_anchors.py  anchor extraction
│   ├── pass2_segments.py segment building, stitching, line -> timestamp mapping
│   ├── ranking.py        judge call, weighted score, tiers
│   ├── qc.py             rule-based checks
│   ├── llm.py            Gemini wrapper: JSON mode, rate limiter, retries
│   ├── config.py         settings, prompts, cast regex loading
│   └── models.py         Pydantic data models
├── tests/         19 tests (pytest)
└── data/
    ├── input/        50 episode files + sample_script.txt
    ├── calibration/  actual_durations.csv (only a placeholder row)
    └── output/       generated results
```

---

## Known issues

These are real, verified problems in the current version. Details and fixes are in the project report.

1. **Promos come out too short.** Pass 2 is told to build promos of 50–150 *words*. In these scripts, camera and action lines make a 20–60 s stretch contain roughly 120–520 words (median ≈ 290 per 40 s). In the saved output only **3 of 11** promos are 20–60 s; the rest are 4–16 s, including the Tier 1 promo (8.8 s).
2. **Word-budget check contradicts the duration check.** Long-enough promos (e.g. 32.7 s, 331 words) are put on **Hold** for exceeding 150 words.
3. **Timestamps are not shown to the LLM.** `Chunk.render()` outputs only `[E1:L5] text`, while the prompts say the text contains exact timestamps. The model is guessing durations.
4. **Hook window is measured in words** (first 10), not seconds (first 3).
5. **Low yield.** Only 11 promos from 50 episodes (14 episodes represented); 22 visual-hook candidates, many of them keyword false positives (`ring` matches "gathering", "hammering"; `tear` matches "tears" regardless of context).
6. **Cross-episode stitching is limited** to episodes inside the same chunk.
7. **5 of 19 tests fail** – they were written for the older single-file format and were not updated (stale expectations: `8.8` vs `8.7` score, `fmt_ts` output format, missing episode 2 in the sample file, a hook keyword that no longer matches).
8. **Calibration is unused.** `actual_durations.csv` holds only the `EXAMPLE` row, and the factor stays at 1.0.
9. **Repo hygiene.** No `.env.example` exists; `.env`, `__pycache__`, `.pytest_cache` and `*.egg-info` are inside the zip; `requirements.txt` includes `pytest`.
10. **Scoring is LLM-only.** The judge is a second call to the same family of model, so scores are not independent of the extractor and are not validated against real viewer data.

## Roadmap (suggested)

- Drive promo length from timestamps (20–60 s) and demote the word budget to a soft warning.
- Print `Start/End` times in each chunk line sent to the model; enforce the hook within 3 s.
- Add a code-side repair step: if a promo is out of range, extend or trim to the nearest line boundary.
- Anchor-first stitching across episodes (no chunk boundary limit).
- Word-boundary regexes for visual-hook keywords.
- Update/replace the failing tests and add a golden-file test for one real episode.
- Validate ranking against a small human-labelled set.
