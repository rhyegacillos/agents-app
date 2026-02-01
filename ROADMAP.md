# 🗺️ Agentic Roadmap

This document tracks the evolution of the application from a "Pipeline" architecture to a **Fully Agentic System**.

## ✅ Phase 1: Foundation (Completed)
- [x] **Agentic Backend Structure:** Modular agents (`extraction`, `summary`, `email`) in `api/agent/`.
- [x] **Intelligent Email Routing:** `email_agent` uses a Router+Tool pattern to decide on translation.
- [x] **Extraction Pipeline:** Parallel processing of Audio, Vision, and Text.
- [x] **Reliability:** Model fallback chains and structured logging.

---

## 🚧 Phase 2: The "Thinking" App (Planned)

The goal is to move from *processing* data to *understanding and acting* on it.

### 1. 📅 Autonomous Coordinator (Next Actions)
**Status:** ✅ Completed
**Goal:** Turn "Next Steps" text into executable actions.
- [x] **Feature:** Parse generated summaries for dates ("Follow up in 2 weeks") and tasks ("Prescribe X").
- [x] **Agent:** `coordinator_agent.py`
- [ ] **Tools:**
    - `extract_actionable_items(text)` (Completed)
    - `check_calendar_availability(date)` (Mock/Google Calendar)
    - `draft_calendar_invite(details)`
- [x] **UX:** Display "Suggested Actions" cards below the summary (e.g., "Book Follow-up").

### 2. 🧠 Long-Term Patient Memory (RAG)
**Status:** ✅ Completed
**Goal:** Enable the agent to "know" the patient's history.
- [x] **Feature:** Retrieve past summaries during generation to highlight changes/trends.
- [x] **Agent:** `memory_agent.py`
- [x] **Tech:** Vector Database (Local JSON VectorStore).
- [x] **Tools:**
    - `store_visit_summary` (Completed)
    - `query_patient_history` (Completed)

### 3. 💬 Interactive Clinical Co-pilot
**Status:** ✅ Completed
**Goal:** Allow doctors to converse with the data.
- [x] **Feature:** Chat interface to query the transcript or request edits.
- [x] **Endpoint:** `/api/chat`
- [x] **Tools:**
    - `search_transcript(query)` (Implicit via RAG)
    - `update_summary_section(section, new_content)`
    - `draft_referral_letter(to_doctor)`

### 4. 📚 Clinical Decision Support (Research)
**Status:** ✅ Completed
**Goal:** Proactive safety checks and information retrieval.
- [x] **Feature:** Auto-detect drug interactions from the summary flow.
- [x] **Agent:** `research_agent.py`
- [x] **Tool:** `check_drug_interactions(medications)` via MCP (Brave Search).
- [x] **Tool:** `search_medical_guidelines(condition)`

### 5. 🕵️ Critic / Reflexion Loop
**Status:** ✅ Completed
**Goal:** Self-correcting quality assurance.
- [x] **Feature:** "Critic Agent" reviews the summary against source notes, uploads, and history.
- [x] **Logic:**
    - Step 1: Generate Summary.
    - Step 2: Critic reviews for hallucinations, missing facts, and contradictions.
    - Step 3: Regenerate with corrections until criteria pass.

---

## 🧭 Phase 3: Fully Agentic System (Planned)

The goal is to move from single-request workflows to **autonomous, long-running agents** that can plan, act, and self-correct across time.

### 1. 🗂️ Task Engine & Schedulers
**Status:** 🔴 Not Started
**Goal:** Allow agents to execute multi-step workflows over time.
- [ ] **Feature:** Task queue for "follow-up in 2 weeks" and "call patient if symptoms worsen."
- [ ] **Tool:** `schedule_task(action, date, metadata)`
- [ ] **Tool:** `run_task(task_id)` with retries + audit logs.
- [ ] **UX:** Background task panel with status + history.

### 2. 🧰 Tool Registry & Permissioning
**Status:** 🔴 Not Started
**Goal:** Centralize tool discovery with safety and approval rules.
- [ ] **Feature:** Dynamic tool registry with allowlist/denylist per plan.
- [ ] **Tool:** `request_approval(action)` for high-risk outputs.
- [ ] **Policy:** "Human-in-the-loop" for prescriptions, referrals, and bookings.

### 3. 🧪 Proposer / Critic / Verifier Loop
**Status:** 🔴 Not Started
**Goal:** Enforce consistency and reduce hallucinations.
- [ ] **Feature:** Separate "Critic Agent" scores summary quality vs transcript.
- [ ] **Feature:** "Verifier Agent" checks safety claims and guideline notes.
- [ ] **Logic:** Regenerate if risk score crosses threshold.

### 3b. 🩺 Patient History Workspace (UI + API)
**Status:** 🟢 In Progress  
**Goal:** Give clinicians a dedicated space to browse longitudinal records with filters.  
- [x] **Feature:** Patient History tab with list/detail views and visit cards.  
- [x] **UX:** Searchable patient dropdown with pagination and last-visit metadata.  
- [x] **Filter:** Date range filtering for visits.  
- [x] **Detail:** Click-through to full visit text with return-to-list control.  
- [x] **API:** Persist evidence snippets per visit for citation surfacing.  
- [x] **API:** Server-side search within visits (by keyword).  
- [x] **UX:** Timeline visualization and “copy summary” actions.  
- [ ] **Backfill:** Optionally regenerate older visits to attach structured evidence.  
- [x] **UX:** Regeneration modal to reuse prior outputs when uploaded notes, template, and visit date match an existing visit; soft-deleted items skip the prompt.  
- [x] **UX:** “Back to main” navigation pill; default date range set to current year-to-date; timeline pills and visit cards reflect deleted/restored state.  

### 4. 🧾 Evidence-Linked Summaries
**Status:** ✅ Completed
**Goal:** Tie clinical summaries to evidence.
- [x] **Feature:** Generate evidence-linked citations for summary statements.
- [x] **Storage:** Save source snippets and links in memory for audit (`visit_evidence`).
- [x] **UX:** Evidence panel toggle with source snippets and research/guideline links.

### 5. 🧭 Persistent Care Plans
**Status:** 🔴 Not Started
**Goal:** Keep unresolved tasks and goals across visits.
- [ ] **Feature:** Patient goals (e.g., BP target) tracked over time.
- [ ] **Feature:** Open tasks carry forward until resolved.
- [ ] **Tool:** `update_care_plan(patient_id, changes)`

### 6. 🧬 Evaluation & Monitoring Harness
**Status:** 🔴 Not Started
**Goal:** Continuous reliability tracking.
- [ ] **Feature:** Regression suite for summaries, actions, and tool use.
- [ ] **Metrics:** Hallucination rate, tool success, safety note accuracy.
- [ ] **Dashboards:** Daily/weekly reports with failure samples.

---

## 📉 Backlog / Nice-to-Have
- [ ] **Voice Interface:** Voice-to-voice interaction with the agent.
- [ ] **Multi-Modal Output:** Generate PDF reports with charts/graphs of vitals.
- [ ] **Integration:** EHR (Epic/Cerner) integration via FHIR.
