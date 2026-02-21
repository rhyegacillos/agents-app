# IdeaGen User Guide

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


## 1) What IdeaGen does

IdeaGen helps you:

- Generate business ideas using AI models
- Compare outputs from different runs (Compare Rank Results / Diff Insight)
- Build Decision Summary Reports from selected saved runs
- Export reports to PDF and/or email (Premium capabilities apply)

---

## 2) Main page layout

On the Product page, you will see:

- **Configuration panel** (left): where you choose inputs before generation
- **Top utility cards** (right, upper area):
  - **Saved Results**
  - **Current Usage** (tokens, API calls, email usage, storage)
- **Results workspace** (right, main area) with 4 tabs:
  - **Generated Results**
  - **Compare Rank Results**
  - **Decision Summary Report**
  - **Execution Plan**

### 2.1 Decision Flow strip and adaptive guidance

Above the tab content, the workspace shows a 4-step flow strip:

1. Generate Results
2. Compare Results
3. Decision Summary
4. Execution Plan

The strip has adaptive onboarding logic:

- **Guided mode**: stronger first-time prompts and prerequisite hints
- **Status mode**: compact progress/status presentation for experienced users

To avoid confusing mode flicker, mode switching uses hysteresis:

- guided -> status when global guidedness `<= 40`
- status -> guided when global guidedness `>= 60`
- between `41-59`, current mode is retained

### 2.2 Step Guide panel (persistent per tab)

A persistent **Step Guide** panel appears under the flow strip on every tab.

It always uses the same structure:

- What you do here
- What you get
- When you should use it
- To move forward

Behavior:

- Collapsible per tab
- Saves collapse preference per user/per tab
- Adaptive default:
  - Guided mode: expanded
  - Status mode: collapsed
- If you manually toggle a tab’s guide, your preference is preserved

---

## 3) Configure before generating

In **Configuration**, set:

1. **Target Industry**
2. **Constraints** (must-have conditions)
3. **AI Persona** (tone/point of view)
4. **AI Models** (select one or multiple depending on plan)
5. Optional Premium advanced settings:
   - **Creativity** (safe ↔ bold)
   - **Idea Diversity** (focused ↔ varied)

Then click **Generate Ideas**.

### Premium recommendation flow

If available in your plan, use **Recommend Combination** after persona/constraints selection to auto-suggest a stronger setup for your chosen industry.

---

## 4) Generated Results tab

After generation:

- Each model output appears in model tabs
- You can switch tabs to compare each model’s generated content
- Ranking information may appear when multiple models are used

If empty, the panel behavior is scenario-based:

- **No saved artifacts (fresh start)**: Generate Ideas is primary.
- **Saved artifacts exist but nothing selected**: Load from Library + Generate Ideas.

Use the Step Guide CTA if you want the recommended next action directly from this tab.

---

## 5) Saved Results modal system

In the **Saved Results** card, there are four buttons:

1. **Generated Results**
2. **Compare Results**
3. **Decision Summary Report**
4. **Execution Plan**

Each opens a modal with the same overall structure and size.

### Modal behavior

- Draggable by header
- Constrained to viewport (cannot be dragged off-screen)
- Close via **Close** button, outside click, or `Esc`
- During long-running actions (Compare / Decision / Execution Plan generation), modal locks:
  - No close
  - No drag
  - Outside click ignored
  - Refresh disabled
- During delete confirmation dialogs, outside clicks no longer close the parent Saved Results modal.

---

## 6) Generated Results (Saved Results modal)

Use this modal section to:

- View list of previously saved runs
- **Load** a run back into workspace
- **Delete** a saved run
- **Delete All** saved generated runs (with confirmation)

Each saved item shows timestamp and configuration summary.

### Delete All behavior

- The **Delete All** button sits beside **Refresh** in Generated mode
- Button is disabled when there are no saved generated runs
- Confirmation modal shows the number of records to remove
- During deletion:
  - modal actions are locked
  - row cards animate to a pending-delete state
  - status shows deleting progress

---

## 7) Compare Results (Saved Results modal)

### Purpose

Run Diff Mode to compare top-ranked outputs from two saved runs.

### Steps

1. Open **Compare Results** from **Saved Results**
2. Pick **Run A** and **Run B**
4. Ensure both runs use the same baseline config (industry/persona/constraints) for cleaner comparison
5. Click **Compare**

### Footer behavior

- Fixed footer shows current status on the left
- Compare button is on the right
- While compare is running, status switches to `Comparing selected runs` with animated dots
- If compare fails, error appears in footer left message
- Clicking **Refresh** clears compare error and restores default footer status

### Saved comparisons

- Previously generated comparisons are listed
- Click **View** to reload that comparison flow
- Click **Delete** to remove one comparison
- Click **Delete All** in the **Saved comparisons** header to remove all saved comparisons
- **Delete All** is disabled when the list is empty

---

## 8) Decision Summary Report (Saved Results modal)

### Purpose

Create a decision-ready report from selected saved runs.

### Steps

1. Open **Decision Summary Report** from **Saved Results**
2. Select runs (**1-5**) or enable **Include all saved results**
3. Choose delivery in footer:
   - **PDF**
   - **Email**
   - **PDF + Email**
4. If email mode is selected, enter recipient email
5. Click **Decision Summary Report** (generate action)

### After generation

- Modal closes automatically
- UI switches to the **Decision Summary Report** tab
- Latest report loads into the tab
- Footer right status changes to a generating message with animated dots during report generation

### Decision Summary readiness behavior (UI)

Decision Summary empty-state uses saved-run availability as top-level readiness:

- if saved runs exist, the screen is considered ready
- if no saved runs exist, Load from Library is disabled and Generate matching run is emphasized

Strict config matching remains an optional filter path in Library/selection flow and does not block the top readiness badge.

### Saved decision summary reports

- Existing reports are listed in modal
- Click **View** to open a saved decision report
- Click **Delete** to remove one saved report
- Click **Delete All** in the **Saved decision summary reports** header to remove all saved reports
- **Delete All** is disabled when the list is empty

---

## 9) Compare Rank Results tab

This tab displays Diff Insight results after compare is run.

You can review:

- Winner run
- Key differences between top outputs
- Summary insight details

---

## 10) Decision Summary Report tab

This tab displays generated/loaded decision reports, including ranking-focused narrative and summary insights.

Use this for:

- Stakeholder sharing
- Documentation of why one run is preferred
- Export/email workflows tied to saved report data

---

## 11) Execution Plan tab

### Purpose

Convert ranked/selected ideas into an implementation and financial decision dossier.

### How generation works

1. Open **Decision Summary Report**
2. Click **Generate Execution Plan**
3. In the selector modal, choose one output variant (per run)
4. Click **Generate Execution Plan**

You can enter Execution Plan directly, but it is generated from decision artifacts.  
If no decision context is loaded, the tab shows readiness cues and points you to Decision Summary/Library actions.

### Finance mode behavior

- Default mode is **Grounded Finance v2**:
  - finance sections are deterministic (not free-form invented)
  - finance is run-conditioned per selected report/output using deterministic rules from:
    - constraints
    - persona
    - selected output signals
    - model confidence
  - scenario probability mix and funnel assumptions can vary by selected report/output
  - narrative sections are LLM-assisted
- Legacy mode (`llm_v1`) exists for compatibility.

### What appears in the report

- Executive decision (`Go` / `Conditional Go` / `No-Go`)
- Decision gates + required actions
- Execution blueprint and resource plan
- Budget, unit economics, monthly projection
- Scenario outcomes
- **Proposal estimate notice** (explicit benchmark disclaimer)
- **Sensitivity analysis** (ARPU, conversion, OpEx stress tests)
- Assumptions + provenance

### Technical label help

- The Execution Plan UI adds inline tooltip icons beside technical labels (for example: Confidence, Year 1 Net, Break-even, ARPU, COGS, OpEx, Cumulative).
- Hover the icon to read plain-language definitions without leaving the report.

### Card-level info pills (new)

Each major Execution Plan card title now includes an **Info** pill tooltip.  
These are written in plain English so any user can quickly understand what each panel means before reading detailed data.

Info pills are available for:

- Execution Plan (overall final-decision package)
- Executive decision
- Business terms and definitions
- Execution blueprint
- Budget and unit economics
- Stakeholder ask
- Scenario outcomes (Year 1)
- Sensitivity analysis
- Monthly financial projection
- Resource plan
- Risk register
- Assumptions
- Profitability recovery plan

Usage:

- Hover (desktop) or tap (click) the **Info** pill beside each card title.
- Tooltip appears near the title and explains the purpose of that panel, what data it contains, and how to interpret it.

### Exports

- **Download PDF**
- **Presentation Report** (deck-style PDF)

Step Guide CTA in Execution tab:

- `Export Plan` action is shown in the Step Guide "To move forward" section when applicable.

### Saved execution plans

- Open from **Saved Results → Execution Plan**
- `View`, `Delete`, and header-level `Delete All`
- Modal supports drag, lock states, and outside-click close (when unlocked)

---

## 12) Current Usage card

Tracks usage with live updates:

- **Tokens** (monthly limit context)
- **API calls**
- **Emails sent**
- **Storage usage**

### Refresh

- Click refresh icon to pull latest usage
- Icon spins while refresh is in progress

---

## 13) Clear vs Delete in workspace

Top-right controls in results workspace:

- **Clear**: clears active tab’s current loaded/displayed content
- **Delete**: permanently deletes selected saved entity (where applicable)

Use Delete carefully—it is persistent removal.

In Saved Results modals, **Delete All** performs bulk permanent deletion with confirmation.

---

## 14) Plan/limit notes

Depending on Free vs Premium, you may have limits on:

- Model count
- Constraints/persona options
- Email sends
- API calls
- Tokens
- Storage

When limits are reached, actions are disabled or return limit messages.

---

## 15) Best-practice workflow (recommended)

1. Configure industry + constraints + persona + models
2. Generate ideas
3. Save useful runs
4. Compare strongest runs in **Compare Results**
5. Build **Decision Summary Report** from finalists
6. Build **Execution Plan** from the winner output variant
7. Export PDF / Presentation Report for stakeholder review

Practical note:

- Compare is recommended for better decision quality.
- Decision Summary can still be produced from a single run when needed.
- Step Guide panel is the fastest way to follow the expected next action without switching context.

---

## 16) Troubleshooting quick checks

- **No results shown**: ensure at least one model is selected and generation was run
- **Compare disabled**: choose two valid runs first
- **Email send blocked**: check email limit in Current Usage
- **Refresh 404 after deploy**: use trailing-slash routes with static export setup (deployment config dependent)
