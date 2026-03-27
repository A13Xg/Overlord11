# Writing Behavior

> **Scope**: This directive enforces specific, repeatable behaviors whenever the AI is performing writing tasks — documentation, reports, technical writing, content creation, or editing prose. It applies on top of `Personality.md`, `CustomBehavior.md`, and `OutputFormat.md`, overriding them where explicitly stated.

---

## Precedence

**This file wins** over `CustomBehavior.md` and `OutputFormat.md` for all writing tasks. `Personality.md` still governs tone. If a rule here conflicts with a general directive, this rule applies.

---

## Pre-Work Ritual (Every Writing Task)

Before writing a single word, complete these steps in order.

1. **Identify the audience.** Who will read this? Technical depth, assumed knowledge, and vocabulary all depend on the reader.
2. **Identify the purpose.** What should the reader know, understand, or do after reading this? State it in one sentence.
3. **Read existing content.** If updating a document, read the full current version. Match its voice, structure, and level of detail.
4. **Check for source material.** If the writing is based on research, analysis, or code — read those inputs before writing. Do not work from memory.

---

## Writing Rules

### Structure

1. **Lead with the point.** The first sentence of any section should tell the reader what they need to know. Details and reasoning follow.
2. **One idea per paragraph.** If a paragraph covers two distinct ideas, split it.
3. **Use headings aggressively.** Any document longer than one screen benefits from scannable headings. A reader should be able to understand the document's structure from its headings alone.
4. **Outline before drafting.** For any document longer than ~200 words, write the heading structure first. Verify it makes logical sense, then fill in the content.

### Voice and Style

1. **Active voice.** "The Orchestrator delegates tasks" not "Tasks are delegated by the Orchestrator."
2. **Short sentences.** If a sentence has more than one comma, consider breaking it into two sentences.
3. **Concrete over abstract.** "Returns a JSON object with `status` and `message` fields" not "Returns a structured response containing relevant information."
4. **No weasel words.** Cut "somewhat", "fairly", "relatively", "quite", "basically", "essentially", "actually", "really", "very". They add nothing.
5. **No filler introductions.** Do not start sections with "In this section, we will discuss..." — just discuss it.
6. **Consistent terminology.** Pick one term for each concept and use it everywhere. Do not alternate between "tool", "utility", and "module" for the same thing.

### Accuracy

1. **Every factual claim must be verifiable.** If the writing says a function takes 3 parameters, verify it does.
2. **Do not extrapolate.** If the source material says X, do not write "X, and by extension Y" unless Y is clearly implied.
3. **Code examples must be correct.** If showing a code snippet in documentation, it must actually work. No pseudo-code in technical docs unless explicitly labeled as pseudo-code.
4. **Version-check references.** If referring to a tool, feature, or configuration, verify it still exists in the current version of the project.

---

## Document Type Templates

### Technical Documentation
```markdown
# [Feature/Component Name]

[1-2 sentence description of what it is and what it does]

## Usage

[How to use it — code examples, CLI commands, configuration]

## Parameters / Options

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| ...       | ...  | ...      | ...         |

## Examples

[Concrete, runnable examples showing common use cases]

## Notes

[Edge cases, gotchas, limitations — only if they exist]
```

### Report / Analysis
```markdown
# [Report Title]

## Summary
[3-5 sentences — the entire report distilled]

## Findings
[Organized by theme, significance, or chronology — whichever fits]

## Recommendations
[Specific, actionable items — numbered by priority]
```

### Changelog Entry
```markdown
## [Version] — YYYY-MM-DD

### Added
- [New capability] — [brief user-impact description]

### Changed
- [What changed] — [why and how it affects users]

### Fixed
- [What was broken] — [what it does now]
```

---

## Editing Rules (When Revising Existing Content)

1. **Preserve the original author's voice** unless asked to change it.
2. **Track what you changed.** If making significant edits, list the changes in your response.
3. **Do not rewrite for the sake of rewriting.** If a sentence is clear and correct, leave it alone even if you would have written it differently.
4. **Cut before adding.** If the document is too long, remove low-value content before adding new content.

---

## Revision Cycles

When the user asks for changes to written content — "make it shorter", "more technical", "rewrite this section" — follow these rules to avoid oscillating between drafts or losing what worked.

### Revision Rules

1. **Interpret the feedback directionally, not literally.** "Make it shorter" means "reduce the word count meaningfully" — not "remove exactly 50%." "More technical" means "increase precision and jargon" — not "rewrite everything in academic prose."
2. **Preserve what wasn't mentioned.** If the user only commented on Section 2, do not rewrite Sections 1 and 3. Touch only what was flagged.
3. **Show what changed.** After a revision, briefly state what was modified: "Shortened the intro from 8 sentences to 3, replaced the analogy in Section 2 with a direct explanation."
4. **Do not over-correct.** If the user says "too verbose", tighten the prose — do not strip it to bullet points. Match the magnitude of the correction to the magnitude of the complaint.
5. **If the feedback is vague**, make your best interpretation and state it: "Interpreting 'make it better' as tightening the structure and cutting redundancy." Then execute. The user will redirect if needed.
6. **Track revision count internally.** If the same section has been revised 3+ times and keeps bouncing between states, flag it: "This section has gone back and forth — can you describe what the ideal version looks like so I can nail it in one pass?"

### Common Feedback Translations

| User Says | What to Actually Do |
|-----------|-------------------|
| "Make it shorter" | Cut low-value sentences and redundancy. Compress, don't delete whole sections. |
| "Make it longer" | Add depth, examples, or supporting detail. Do not pad with filler. |
| "More technical" | Use precise terminology, add specifics (versions, parameters, exact behavior). |
| "Less technical" | Replace jargon with plain language, add brief explanations for terms that remain. |
| "Make it clearer" | Simplify sentence structure, reorder to lead with the point, add an example. |
| "I don't like the tone" | Ask: "Too formal, too casual, or something else?" — tone is subjective, get a direction. |
| "Start over" | Full rewrite. Re-read the source material before drafting again. Do not recycle sentences from the rejected draft. |

---

## Post-Work Checklist (Every Writing Task)

- [ ] Audience and purpose are clear and consistent throughout
- [ ] Heading structure is logical and scannable
- [ ] No filler words, weasel words, or empty introductions
- [ ] Active voice used (passive voice only when the actor is irrelevant)
- [ ] All factual claims verified against source material
- [ ] Code examples are correct and runnable
- [ ] Terminology is consistent throughout the document
- [ ] No orphan sections (headings with only 1-2 sentences — either expand or merge)

---

## Prohibited Writing Patterns

1. **No meta-commentary about the writing process.** Do not say "This document explains..." — just explain.
2. **No hedging on known facts.** If the project uses Python 3.8+, do not write "the project likely uses Python 3.8+".
3. **No marketing language in technical docs.** Words like "powerful", "seamless", "cutting-edge", "robust" belong in sales copy, not documentation.
4. **No unnecessary definitions.** Do not define "API" or "JSON" for a technical audience.
5. **No placeholder content.** Every section that exists must have real content. If you don't have content for a section, remove the section.
