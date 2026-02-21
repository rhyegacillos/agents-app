# UX Flow Guide (IdeaGen)

This guide explains how a non-technical user moves through the app to generate ideas, compare runs, and create decision-ready outputs.

## Documentation Sync: Adaptive Decision Flow + Step Guide (2026-02-20)

This document is synchronized with the latest UX/flow implementation in `pages/product.tsx`.

- **Adaptive flow modes**: UI now shifts between `guided` and `status` modes.
- **Hysteresis guard**: mode switching uses `guided -> status` at `<= 40` and `status -> guided` at `>= 60` to avoid flip-flop around a single threshold.
- **Persistent Step Guide**: every workspace step includes a structured guide panel (`What you do`, `What you get`, `When to use`, `To move forward`).
- **Per-step memory**: collapse/expand is saved per user and per step using local storage (`collapsedByStep`, `touchedByStep`).
- **Adaptive Step Guide defaults**: untouched guides auto-expand in guided mode and auto-collapse in status mode.
- **User override priority**: once a user manually toggles a step guide, that preference is preserved and not auto-overridden.
- **Generated empty-state scenarios**: first-time vs returning-with-library cases are explicitly separated for clearer onboarding.
- **Decision Summary behavior**: supports single-run and multi-run (1-5) synthesis; compare-first is recommended but not mandatory.
- **Compare behavior**: compares two selected saved runs and surfaces winner/diff insight; best quality when config alignment is preserved.
- **Execution handoff**: Decision Summary remains the source artifact for Execution Plan generation and export workflow.
- **Scope note**: this update is primarily frontend UX/state orchestration; backend endpoint contracts remain unchanged unless otherwise stated in backend/API docs.


## Key Terms
- **Constraints**: must-have rules for the output (budget, compliance, stack limits, timeline).
- **Persona**: the perspective/style of the response (for example operator-focused vs founder-focused).
- **Run**: one generated result set saved from the Generated Results step.

---

## Decision Flow system (global behavior)

The workspace uses a 4-step flow strip:

1. Generate Results
2. Compare Results
3. Decision Summary
4. Execution Plan

The flow strip has adaptive behavior:

- **Guided mode** (newer users): stronger prerequisite and next-step guidance.
- **Status mode** (experienced users): compact status and artifact-count view.

Mode switches use hysteresis to prevent UI flip/flop:

- switch to status only at guidedness `<= 40`
- switch to guided only at guidedness `>= 60`
- between `41-59`, mode remains unchanged

---

## Persistent Step Guide panel (all tabs)

Under the flow strip, each tab shows a persistent **Step Guide** panel with the same structure:

- What you do here
- What you get
- When you should use it
- To move forward

Behavior:

- Collapsible per tab.
- Collapse state is saved per user and per tab.
- Defaults are adaptive:
  - guided mode: expanded
  - status mode: collapsed
- Once a user manually toggles it on a tab, that manual preference is preserved.

---

## Flow 1: Generate Ideas

1. Pick **Target Industry**.
2. Select **Constraints**.
3. Select **AI Persona**.
4. Select one or more **AI Models**.
5. Click **Generate Ideas**.

What you get:

- One saved run (per generation action).
- Per-model output cards/tabs for the selected models.
- Model ranking block when multi-model ranking is available.

Generated empty-state scenarios:

- **Fresh user** (no artifacts): CTA is Generate Ideas.
- **Returning user with saved artifacts but no selected run**: CTA is Load from Library (runs) and Generate Ideas.

---

## Flow 2: Compare Results (Diff Insight)

Use when you want to compare two saved runs and identify a winner.

1. Open **Compare Results** tab.
2. Either:
   - load a saved comparison from Library, or
   - use the inline Compare Builder.
3. Select **Run A** and **Run B**.
4. Click **Compare**.

Important:

- Compare requires exactly 2 selected runs.
- Best quality is achieved when both runs share the same Industry + Persona + Constraints + model set.

What you get:

- Winner + rationale.
- Diff insight and key changes.
- Saved comparison artifact for reuse.

---

## Flow 3: Decision Summary

Use when you want a stakeholder-ready decision report.

1. Open **Decision Summary** tab.
2. Choose one path:
   - Load from Library (existing decision summaries or runs), or
   - Generate matching run for current configuration.
3. Select **1-5 runs** in the decision selection view.
4. Click **Decision Summary** to generate.

Important:

- Compare is recommended before Decision Summary, but not mandatory.
- Decision Summary supports single-run synthesis and multi-run ranking.

What you get:

- Ranked recommendation narrative.
- Risks and next-step framing.
- Saved decision summary artifact.

---

## Flow 4: Execution Plan

Use when you are ready to translate a decision into execution.

1. Open **Execution Plan** tab.
2. Load a decision summary from Library or generate from Decision step.
3. Click **Generate Execution Plan**.
4. Select the target output variant if prompted.

What you get:

- Go/Conditional Go/No-Go recommendation.
- Deterministic finance sections (Grounded Finance v2).
- Resource plan, milestones, risks, and actions.
- PDF and presentation report exports.

---

## Library behavior across steps

The Library card is the central artifact entry point:

- Runs
- Comparisons
- Decision Summaries
- Execution Plans

Use Library when:

- you clear current context,
- you want to backtrack non-linearly,
- you want to reload historical artifacts without re-generating.

---

## Common Tips

- If comparison fails, first verify run compatibility (Industry/Persona/Constraints/model set).
- If ranking is not shown, check if only one model was used for that run.
- If you are unsure of the next action, use the tab’s Step Guide panel CTA.
- For first-time use: Generate -> Compare -> Decision -> Execution Plan remains the recommended path.
