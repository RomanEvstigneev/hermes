---
name: baoyu
description: "Baoyu creative suite — knowledge comics (知识漫画) and infographics (信息图). 2 modes: comic (art × tone × layout) and infographic (21 layouts × 21 styles). From JimLiu/baoyu-skills."
version: 1.0.0
author: 宝玉 (JimLiu), ported by Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [baoyu, comic, infographic, knowledge-comic, visual-summary, creative, image-generation, 知识漫画, 信息图]
    related_skills: []
    homepage: https://github.com/JimLiu/baoyu-skills
---

# Baoyu Creative Suite

Two creative image-generation workflows from the same upstream project (baoyu-skills by JimLiu).

| Mode | Description | Options |
|------|-------------|---------|
| **Comic** (知识漫画) | Knowledge comics — educational, biography, tutorial | 6 art styles × 7 tones × 7 layouts + 5 presets |
| **Infographic** (信息图) | Visual summaries and infographics | 21 layouts × 21 styles |

Both modes use the `image_generate` tool (prompt-only, no reference images). Both output to `{mode}/{topic-slug}/` with a consistent file structure.

## When to Use

Load this skill when the user asks to create:
- A knowledge/educational comic, biography comic, tutorial comic ("知识漫画", "教育漫画")
- An infographic, visual summary, information graphic ("信息图", "可视化", "高密度信息大图")
- Any "Baoyu" or "baoyu-skills" workflow

Choose the mode based on user intent:
- **Narrative/sequential** → comic mode (panels, storyboard, characters)
- **Information-dense** → infographic mode (structured content, layouts, styles)

## Common Setup

Both modes share:
- Source: user-supplied text (inline, file, URL) or topic
- Output directory: `{mode}/{topic-slug}/`
- Slug: 2-4 words kebab-case from topic
- Conflict resolution: append `-YYYYMMDD-HHMMSS` timestamp
- Source file saved as `source-{slug}.{ext}`
- Secrets stripped from all output (scan for API keys, tokens, credentials)
- Language: detect from user conversation language or explicit option
- Image generation via `image_generate` tool (prompt + aspect_ratio only)

---

# Mode 1: Knowledge Comic (知识漫画)

Create original knowledge comics with flexible art style × tone × layout combinations.

## Comic Options

| Option | Values |
|--------|--------|
| Art style | `ligne-claire` (default), `manga`, `realistic`, `ink-brush`, `chalk`, `minimalist` |
| Tone | `neutral` (default), `warm`, `dramatic`, `romantic`, `energetic`, `vintage`, `action` |
| Layout | `standard` (default), `cinematic`, `dense`, `splash`, `mixed`, `webtoon`, `four-panel` |
| Aspect | `3:4` (default, portrait), `4:3` (landscape), `16:9` (widescreen) |
| Language | `auto` (default), `zh`, `en`, `ja`, etc. |

### Presets (special combinations)

| Preset | Art + Tone + Layout | Best For |
|--------|---------------------|----------|
| `ohmsha` | manga + neutral | Visual metaphors, gadget reveals |
| `wuxia` | ink-brush + action | Qi effects, combat visuals |
| `shoujo` | manga + romantic | Decorative, romantic beats |
| `concept-story` | manga + warm | Growth arcs, visual symbolism |
| `four-panel` | minimalist + neutral + four-panel | 起承转合 structure |

### Partial Workflows

| Option | Description |
|--------|-------------|
| Storyboard only | Generate storyboard only, skip prompts and images |
| Prompts only | Generate storyboard + prompts, skip images |
| Images only | Generate images from existing prompts directory |
| Regenerate N | Regenerate specific page(s) only (e.g., `3` or `2,5,8`) |

## Comic File Structure

```
comic/{topic-slug}/
├── source-{slug}.{ext}
├── analysis.md
├── storyboard.md
├── characters/
│   ├── characters.md
│   └── characters.png       # character reference sheet
├── prompts/
│   ├── NN-cover-[slug].md
│   └── NN-page-[slug].md
├── NN-cover-[slug].png
├── NN-page-[slug].png
└── refs/                    # optional reference images
    └── NN-ref-{slug}.{ext}
```

## Comic Workflow

### Progress Checklist
```
Comic Progress:
- [ ] Step 1: Setup & Analyze (1.1 Analyze content, 1.2 Check existing dir)
- [ ] Step 2: Confirmation — Style & options (REQUIRED — use clarify)
- [ ] Step 3: Generate storyboard + characters
- [ ] Step 4: Review outline (conditional)
- [ ] Step 5: Generate prompts
- [ ] Step 6: Review prompts (conditional)
- [ ] Step 7: Generate images (7.1 Character sheet if needed, 7.2 Pages)
- [ ] Step 8: Completion report
```

### Step 1: Setup & Analyze
1. Save source content → `source-{slug}.md` (backup existing first)
2. Analyze: topic, complexity, tone, audience, source language
3. Save analysis → `analysis.md` (backup existing first)
4. Strip any credentials/secrets from all output files

### Step 2: Confirm Options (REQUIRED)
Use `clarify` to confirm options one question at a time. Ask in order:
1. **Style combo** — Present presets first (ohmsha, wuxia, shoujo, concept-story, four-panel) and/or art+tone recommendations. Let user pick or customize.
2. **Layout** — Only ask if four-panel layout wasn't already chosen via preset.
3. **Aspect ratio** — Only ask if different from default.
4. **Language** — Only if source ≠ user language.
5. **Review gates** — Ask "review storyboard before prompts?" and "review prompts before images?"

**Timeout handling**: If `clarify` times out, treat that one answer as default but continue asking remaining questions. Surface defaults visibly in next message.

### Step 3: Generate Storyboard + Characters
Write to files:
- `storyboard.md` — panel breakdown with scene descriptions, dialogue, visual notes, aspect_ratio per panel
- `characters/characters.md` — character definitions with physical traits, personality, role

**Character consistency** is driven by text descriptions in `characters/characters.md`, not by images — `image_generate` does not accept reference images.

### Step 4: Review Outline (Conditional)
Only if user requested it in Step 2. Present storyboard for approval.

### Step 5: Generate Prompts
Write one prompt file per page to `prompts/NN-{cover|page}-[slug].md`. Each prompt must:
- Include character descriptions embedded inline from `characters/characters.md`
- Include art style, tone, layout instructions
- Include aspect ratio reference

### Step 6: Review Prompts (Conditional)
Only if user requested it in Step 2.

### Step 7: Generate Images
**7.1 Character sheet** — `characters/characters.png`, landscape aspect ratio. Generate for multi-page comics with recurring characters. Skip for simple presets.

**7.2 Pages** — For each prompt file, call `image_generate`, then download the URL:
```bash
curl -fsSL "<url>" -o /abs/path/comic/{slug}/NN-page-{slug}.png
```

**CRITICAL: Use absolute paths for `curl -o`** — never rely on shell CWD persistence across batches. The CWD can shift between terminal sessions.

Aspect ratio mapping:
| Comic ratio | image_generate format |
|-------------|----------------------|
| 3:4, 9:16, 2:3 | portrait |
| 4:3, 16:9, 3:2 | landscape |
| 1:1 | square |

### Step 8: Completion Report
Report: topic, art style + tone, layout, aspect ratio, page count, output path, files created.

## Reference Images (Comic)

When the user supplies a reference image:
- File path → copy to `refs/NN-ref-{slug}.{ext}` for provenance
- Pasted image with no path → ask user for path via clarify
- No reference → skip

Extract style/palette traits as text descriptions that get embedded in every page prompt:
| Usage | Effect |
|-------|--------|
| `style` | Extract traits (line treatment, texture, mood) → append to every page prompt |
| `palette` | Extract hex colors → append to every page prompt |
| `scene` | Extract composition/subject notes → append to relevant page prompts |

## Page Modification

| Action | Steps |
|--------|-------|
| Edit | Update prompt file → regenerate image → download new PNG |
| Add | Create prompt at position → generate → renumber subsequent → update storyboard |
| Delete | Remove files → renumber subsequent → update storyboard |

## Comic Pitfalls
- **Step 2 confirmation required** — do not skip
- **Steps 4/6 conditional** — only if user requested in Step 2
- **Always download** the URL returned by `image_generate` — ephemeral URLs
- **Use absolute paths for `curl -o`** — CWD is unreliable across terminal batches
- **Character consistency** driven by text descriptions in prompts, not by the PNG sheet
- Strip secrets from source content before writing any output file
- Auto-retry once on image generation failure
- Use stylized alternatives for sensitive public figures

---

# Mode 2: Infographic (信息图)

Two dimensions: **layout** (information structure) × **style** (visual aesthetics). Freely combine any layout with any style.

## Infographic Options

| Option | Values |
|--------|--------|
| Layout | 21 options (see below), default: `bento-grid` |
| Style | 21 options (see below), default: `craft-handmade` |
| Aspect | Landscape (16:9), portrait (9:16), square (1:1), or custom W:H |
| Language | `en` (default), `zh`, `ja`, etc. |

### Layout Gallery (21)

| Layout | Best For |
|--------|----------|
| `linear-progression` | Timelines, processes, tutorials |
| `binary-comparison` | A vs B, before-after, pros-cons |
| `comparison-matrix` | Multi-factor comparisons |
| `hierarchical-layers` | Pyramids, priority levels |
| `tree-branching` | Categories, taxonomies |
| `hub-spoke` | Central concept with related items |
| `structural-breakdown` | Exploded views, cross-sections |
| `bento-grid` | Multiple topics, overview (default) |
| `iceberg` | Surface vs hidden aspects |
| `bridge` | Problem-solution |
| `funnel` | Conversion, filtering |
| `isometric-map` | Spatial relationships |
| `dashboard` | Metrics, KPIs |
| `periodic-table` | Categorized collections |
| `comic-strip` | Narratives, sequences |
| `story-mountain` | Plot structure, tension arcs |
| `jigsaw` | Interconnected parts |
| `venn-diagram` | Overlapping concepts |
| `winding-roadmap` | Journey, milestones |
| `circular-flow` | Cycles, recurring processes |
| `dense-modules` | High-density modules, data-rich guides |

### Style Gallery (21)

| Style | Description |
|-------|-------------|
| `craft-handmade` | Hand-drawn, paper craft (default) |
| `claymation` | 3D clay figures, stop-motion |
| `kawaii` | Japanese cute, pastels |
| `storybook-watercolor` | Soft painted, whimsical |
| `chalkboard` | Chalk on black board |
| `cyberpunk-neon` | Neon glow, futuristic |
| `bold-graphic` | Comic style, halftone |
| `aged-academia` | Vintage science, sepia |
| `corporate-memphis` | Flat vector, vibrant |
| `technical-schematic` | Blueprint, engineering |
| `origami` | Folded paper, geometric |
| `pixel-art` | Retro 8-bit |
| `ui-wireframe` | Grayscale interface mockup |
| `subway-map` | Transit diagram |
| `ikea-manual` | Minimal line art |
| `knolling` | Organized flat-lay |
| `lego-brick` | Toy brick construction |
| `pop-laboratory` | Blueprint grid, coordinate markers |
| `morandi-journal` | Hand-drawn doodle, warm Morandi tones |
| `retro-pop-grid` | 1970s retro pop art, Swiss grid |
| `hand-drawn-edu` | Macaron pastels, hand-drawn wobble |

### Recommended Combinations

| Content Type | Layout + Style |
|--------------|----------------|
| Timeline/History | `linear-progression` + `craft-handmade` |
| Step-by-step | `linear-progression` + `ikea-manual` |
| A vs B | `binary-comparison` + `corporate-memphis` |
| Hierarchy | `hierarchical-layers` + `craft-handmade` |
| Overlap | `venn-diagram` + `craft-handmade` |
| Conversion | `funnel` + `corporate-memphis` |
| Cycles | `circular-flow` + `craft-handmade` |
| Technical | `structural-breakdown` + `technical-schematic` |
| Metrics | `dashboard` + `corporate-memphis` |
| Educational | `bento-grid` + `chalkboard` |
| Journey | `winding-roadmap` + `storybook-watercolor` |
| Categories | `periodic-table` + `bold-graphic` |
| Educational Diagram | `hub-spoke` + `hand-drawn-edu` |

### Keyword Shortcuts

| User Keyword | Layout | Recommended Styles | Aspect | Prompt Notes |
|--------------|--------|--------------------|--------|--------------|
| 高密度信息大图 / high-density-info | `dense-modules` | morandi-journal, pop-laboratory, retro-pop-grid | portrait | — |
| 信息图 / infographic | `bento-grid` | craft-handmade | landscape | Minimalist: clean canvas, ample whitespace |

## Infographic File Structure

```
infographic/{topic-slug}/
├── source-{slug}.{ext}
├── analysis.md
├── structured-content.md
├── prompts/infographic.md
└── infographic.png
```

## Infographic Workflow

### Step 1: Analyze Content
1. Save source content → `source.md` (backup if exists)
2. Analyze: topic, data type, complexity, tone, audience, language
3. Save analysis → `analysis.md` (backup if exists)

### Step 2: Generate Structured Content → `structured-content.md`
Transform content into infographic structure:
- Title and learning objectives
- Sections with: key concept, content (verbatim), visual element, text labels
- All statistics/quotes copied exactly
- Design instructions from user
- No new information. Strip credentials.

### Step 3: Recommend Combinations
- Check Keyword Shortcuts first (auto-select associated layout)
- Otherwise recommend 3-5 layout × style combinations based on data structure, content tone, audience

### Step 4: Confirm Options (use clarify)
**Q1 — Combination**: Present 3+ layout×style combos.
**Q2 — Aspect**: Ask aspect ratio preference.
**Q3 — Language**: Only if source ≠ user language.

### Step 5: Generate Prompt → `prompts/infographic.md`
Combine layout definition, style definition, base template, and structured content. Backup existing prompt file first.

Aspect ratio to image_generate mapping:
- Custom W:H ratio → nearest named (landscape/portrait/square)
- 16:9 → landscape, 9:16 → portrait, 1:1 → square

### Step 6: Generate Image
Call `image_generate`, auto-retry once on failure. Save result.

### Step 7: Output Summary
Report: topic, layout, style, aspect, language, output path, files created.

## Infographic Pitfalls
- **Data integrity is paramount** — never summarize, paraphrase, or alter source statistics
- **Strip secrets** — scan for API keys, tokens, or credentials in source
- **Style consistency** — apply the same style definition across the entire infographic
- `image_generate` only supports landscape/portrait/square — map custom ratios to nearest
- **One concept per section** — overloading sections reduces readability

## Common Pitfalls (Both Modes)

1. **Always download** `image_generate` URLs to local files — they're ephemeral
2. **Use absolute paths** for `curl -o` — never rely on terminal CWD persistence across batches
3. **Auto-retry once** on image generation failure
4. **Strip secrets** from all source content before writing output
5. **Step 2 user confirmation** is required in both modes — use clarify
6. **Backup existing files** before overwriting (`-backup-YYYYMMDD-HHMMSS` suffix)
7. **Language detection**: use user's input language for all interactions including confirmations, updates, summaries. Technical terms stay in English.

## Reference Files

The original baoyu-comic and baoyu-infographic skills had extensive reference files for art styles, tones, layouts, presets, workflows, and templates. These have been archived but are accessible at:
- `~/.hermes/skills/.archive/baoyu-comic/references/`
- `~/.hermes/skills/.archive/baoyu-infographic/references/`