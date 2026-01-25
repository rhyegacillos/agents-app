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
**Status:** 🔴 Not Started
**Goal:** Enable the agent to "know" the patient's history.
- [ ] **Feature:** Retrieve past summaries during generation to highlight changes/trends.
- [ ] **Agent:** `memory_agent.py`
- [ ] **Tech:** Vector Database (e.g., ChromaDB/PGVector).
- [ ] **Tools:**
    - `store_visit_summary(patient_id, vector)`
    - `query_patient_history(patient_id, query)`

### 3. 💬 Interactive Clinical Co-pilot
**Status:** 🔴 Not Started
**Goal:** Allow doctors to converse with the data.
- [ ] **Feature:** Chat interface to query the transcript or request edits.
- [ ] **Endpoint:** `/api/chat`
- [ ] **Tools:**
    - `search_transcript(query)`
    - `update_summary_section(section, new_content)`
    - `draft_referral_letter(to_doctor)`

### 4. 📚 Clinical Decision Support (Research)
**Status:** 🔴 Not Started
**Goal:** Proactive safety checks and information retrieval.
- [ ] **Feature:** Auto-detect drug interactions or complex conditions.
- [ ] **Agent:** `research_agent.py`
- [ ] **Tools:**
    - `check_drug_interaction(med_a, med_b)`
    - `search_medical_guidelines(condition)`

### 5. 🕵️ Critic / Reflexion Loop
**Status:** 🔴 Not Started
**Goal:** Self-correcting quality assurance.
- [ ] **Feature:** "Critic Agent" reviews the summary against the raw transcript before showing it to the user.
- [ ] **Logic:**
    - Step 1: Generate Summary.
    - Step 2: Critic reviews for hallucinations/missed details.
    - Step 3: (If needed) Regenerate with corrections.

---

## 📉 Backlog / Nice-to-Have
- [ ] **Voice Interface:** Voice-to-voice interaction with the agent.
- [ ] **Multi-Modal Output:** Generate PDF reports with charts/graphs of vitals.
- [ ] **Integration:** EHR (Epic/Cerner) integration via FHIR.
