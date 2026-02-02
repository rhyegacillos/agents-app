# IdeaGen User Guide

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
- **Results workspace** (right, main area) with 3 tabs:
  - **Generated Results**
  - **Compare Rank Results**
  - **Decision Summary Report**

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

If empty, use the quick-start instructions shown in the blank state.

---

## 5) Saved Results modal system

In the **Saved Results** card, there are three buttons:

1. **Generated Results**
2. **Compare Results**
3. **Decision Summary Report**

Each opens a modal with the same overall structure and size.

### Modal behavior

- Draggable by header
- Constrained to viewport (cannot be dragged off-screen)
- Close via **Close** button, outside click, or `Esc`
- During long-running actions (Compare / Decision report generation), modal locks:
  - No close
  - No drag
  - Outside click ignored
  - Refresh disabled

---

## 6) Generated Results (Saved Results modal)

Use this modal section to:

- View list of previously saved runs
- **Load** a run back into workspace
- **Delete** a saved run

Each saved item shows timestamp and configuration summary.

---

## 7) Compare Results (Saved Results modal)

### Purpose

Run Diff Mode to compare top-ranked outputs from two saved runs.

### Steps

1. Open **Compare Results** from **Saved Results**
2. Click **Show** in “Select two runs”
3. Pick **Run A** and **Run B**
4. Ensure both runs use the same baseline config (industry/persona/constraints) for cleaner comparison
5. Click **Compare**

### Footer behavior

- Fixed footer shows current status on the left
- Compare button is on the right
- If compare fails, error appears in footer left message
- Clicking **Refresh** clears compare error and restores default footer status

### Saved comparisons

- Previously generated comparisons are listed
- Click **View** to reload that comparison flow

---

## 8) Decision Summary Report (Saved Results modal)

### Purpose

Create a decision-ready report from selected saved runs.

### Steps

1. Open **Decision Summary Report** from **Saved Results**
2. Select runs (up to allowed amount) or enable **Include all saved results**
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

### Saved decision summary reports

- Existing reports are listed in modal
- Click **View** to open a saved decision report

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

## 11) Current Usage card

Tracks usage with live updates:

- **Tokens** (monthly limit context)
- **API calls**
- **Emails sent**
- **Storage usage**

### Refresh

- Click refresh icon to pull latest usage
- Icon spins while refresh is in progress

---

## 12) Clear vs Delete in workspace

Top-right controls in results workspace:

- **Clear**: clears active tab’s current loaded/displayed content
- **Delete**: permanently deletes selected saved entity (where applicable)

Use Delete carefully—it is persistent removal.

---

## 13) Plan/limit notes

Depending on Free vs Premium, you may have limits on:

- Model count
- Constraints/persona options
- Email sends
- API calls
- Tokens
- Storage

When limits are reached, actions are disabled or return limit messages.

---

## 14) Best-practice workflow (recommended)

1. Configure industry + constraints + persona + models
2. Generate ideas
3. Save useful runs
4. Compare strongest runs in **Compare Results**
5. Build **Decision Summary Report** from finalists
6. Export PDF / send email for stakeholder review

---

## 15) Troubleshooting quick checks

- **No results shown**: ensure at least one model is selected and generation was run
- **Compare disabled**: choose two valid runs first
- **Email send blocked**: check email limit in Current Usage
- **Refresh 404 after deploy**: use trailing-slash routes with static export setup (deployment config dependent)

