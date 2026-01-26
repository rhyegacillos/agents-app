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
**Status:** 🔴 Not Started
**Goal:** Self-correcting quality assurance.
- [ ] **Feature:** "Critic Agent" reviews the summary against the raw transcript before showing it to the user.
- [ ] **Logic:**
    - Step 1: Generate Summary.
    - Step 2: Critic reviews for hallucinations/missed details.
    - Step 3: (If needed) Regenerate with corrections.

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

### 4. 🧾 Evidence-Linked Summaries
**Status:** 🔴 Not Started
**Goal:** Tie clinical safety notes to evidence.
- [ ] **Feature:** Require citations for all guideline or drug interaction notes.
- [ ] **Storage:** Save source snippets in memory for audit.
- [ ] **UX:** "Evidence" toggle to show sources inline.

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
