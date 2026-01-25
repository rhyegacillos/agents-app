# Agentic Healthcare SaaS (AWS)

This project is a sophisticated Healthcare SaaS application featuring a **fully agentic backend architecture**. It utilizes large language models (LLMs) to automate complex clinical workflows, including patient data extraction, consultation summarization, and intelligent email dispatch.

## ✨ Main Features & User Guide

The application provides a seamless interface for doctors to manage patient consultations. Here is how to interact with the system:

### 1. Intelligent Consultation Capture
Instead of typing notes manually, you can upload various data sources directly through the UI:
*   **Audio Recordings:** Upload MP3/WAV files of your consultation. The system will automatically transcribe them.
*   **Handwritten Notes:** Take a photo of your handwritten prescriptions or notes. The Vision Agent will digitize them.
*   **Existing Documents:** Upload PDF or DOCX referral letters or past history.

### 2. Auto-Generated Clinical Summaries
Once your data is uploaded:
1.  Click **"Generate Summary"**.
2.  The **Summary Agent** analyzes all inputs (notes, transcripts, images) and cross-references them.
3.  It produces a structured clinical note (SOAP, Discharge Summary, etc.) based on your selected template.
4.  The result streams in real-time to your dashboard.

### 3. Smart Email Dispatch (Agentic)
After reviewing the summary:
1.  Go to the **"Email Patient"** tab.
2.  Review the drafted email.
3.  **Language Selection:** If you select a language other than English (e.g., Spanish), the **Email Agent** will automatically detect this intent, translate the content using a specialized tool, and then send it.
4.  Click **"Send"** to dispatch via Resend.

### 4. Autonomous Action Coordinator
The system doesn't just summarize; it plans.
*   **Action Extraction:** It automatically parses the "Next Steps" of your summary.
*   **Structured Cards:** It presents actionable items (e.g., "Schedule Follow-up", "Prescribe Amoxicillin") as structured cards, ready for future one-click execution.

---

## 🧠 Agentic Architecture

Unlike traditional monolithic applications, this backend is composed of specialized **AI Agents**, each responsible for a distinct domain of the clinical workflow. This "Agentic" approach allows for:

1.  **Separation of Concerns:** Each agent handles its own logic, tools, and error recovery.
2.  **Intelligent Routing:** Agents can dynamically decide which tools to use (e.g., "Should I translate this email?") based on context rather than hard-coded rules.
3.  **Resilience:** Failures in one agent (e.g., translation) can be handled gracefully with retries and fallbacks without crashing the entire request.

### Core Agents

The system is powered by four primary agents located in `api/agent/`:

#### 1. Extraction Agent (`extraction_agent.py`)
*   **Role:** The "senses" of the system. It handles the ingestion of unstructured medical data.
*   **Capabilities:**
    *   **File Parsing:** Extracts text from PDF, DOCX, and TXT files.
    *   **Audio Transcription:** Uses OpenAI Whisper to transcribe audio consultation recordings (MP3, WAV, etc.).
    *   **Vision Processing:** Uses GPT-4o Vision to transcribe handwritten medical prescriptions from images.
    *   **Entity Extraction:** Structurally extracts doctor and patient contact details from raw text.
*   **Pattern:** **Async Pipeline**. It runs multiple extraction tasks in parallel to minimize latency.

#### 2. Summary Agent (`summary_agent.py`)
*   **Role:** The "brain" of the clinical synthesis.
*   **Capabilities:**
    *   **Orchestration:** Orchestrates the entire pipeline: calls the Extraction Agent -> aggregates context -> prompts the LLM -> streams the result.
    *   **Contextual Summarization:** Generates medical summaries (SOAP, Discharge, Referral) based on the specific visit type.
    *   **Streaming:** Returns data to the frontend token-by-token for a responsive UX.
*   **Pattern:** **Orchestrator Pipeline**. It acts as a controller that manages the flow of data between sub-components.

#### 3. Coordinator Agent (`coordinator_agent.py`)
*   **Role:** The "planner".
*   **Capabilities:**
    *   **Intent Recognition:** Reads the generated summary to identify implicit tasks.
    *   **Structured Output:** Converts unstructured text (e.g., "See patient in 2 weeks") into structured JSON data (e.g., `{"type": "schedule", "date": "2025-02-14"}`).
*   **Pattern:** **Extractor**. It runs as a post-processing step to turn text into data.

#### 4. Email Agent (`email_agent.py`)
*   **Role:** The "dispatcher".
*   **Capabilities:**
    *   **Intelligent Routing:** Uses an **Agent Loop** to analyze the request and decide on the necessary steps.
    *   **Tool Usage:**
        *   `translate_email`: Dynamically translates content if the target language is not English.
        *   `send_email_final`: Dispatches the final email via Resend.
*   **Pattern:** **Router + Tools**. Unlike a standard script, this agent *decides* its course of action. For example, if asked to send an email in Spanish, it autonomously recognizes the need to call the translation tool first, then the sending tool.

---

## 🛠️ Reliability Engineering

To ensure production-grade reliability, the system implements:

### Model Fallback Strategy (`utils.py`)
We do not rely on a single AI model. The system uses a **Cascading Fallback Chain**:
1.  **Primary:** `gpt-5-nano` (Hypothetical efficient model) - Optimized for speed and cost.
2.  **Secondary:** `gpt-4o-mini` - Reliable standard model.
3.  **Fallback:** `gpt-3.5-turbo` - Legacy robust model.

If the primary model fails (rate limit, outage, or server error), the system **automatically retries** with the next model in the chain, ensuring high availability for critical clinical tasks.

### Observability
All agents utilize a centralized logging system (`get_logger`) to trace:
*   Tool execution flow (e.g., "Agent calling tool: translate_email").
*   Model fallback events (e.g., "Error with model gpt-5-nano, retrying with gpt-4o-mini").
*   Pipeline stages.

---

## 🚀 Getting Started

First, run the development server:

```bash
npm run dev
# or
yarn dev
# or
pnpm dev
# or
bun dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

### Environment Variables

Ensure you have the following keys in your `.env.local`:
*   `OPENAI_API_KEY`: For LLM, Vision, and Audio services.
*   `RESEND_API_KEY`: For sending emails.
*   `CLERK_JWKS_URL`: For authentication.

## Folder Structure

*   `api/agent/`: Contains all agent logic.
    *   `extraction_agent.py`: File/Audio/Image processing.
    *   `summary_agent.py`: Summarization logic & pipeline orchestration.
    *   `email_agent.py`: Agentic router for email dispatch.
    *   `utils.py`: Shared utilities (Fallback logic, Logging).
    *   `models.py`: Shared Pydantic data models.
*   `api/index.py`: API Gateway/Router that delegates requests to specific agents.