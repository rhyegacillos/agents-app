# Agentic Healthcare SaaS (AWS)

This project is a sophisticated Healthcare SaaS application featuring a **fully agentic backend architecture**. It utilizes large language models (LLMs) to automate complex clinical workflows, including patient data extraction, consultation summarization, and intelligent email dispatch.

## ✨ Main Features & User Guide

The application provides a seamless interface for doctors to manage patient consultations. Here is how to interact with the system:

### Asynchronous Job Management & Real-time Streaming
Leveraging **Upstash Redis**, the system ensures that long-running tasks, like summary generation, are handled efficiently and reliably. This provides real-time updates to the UI and guarantees that your work is always saved and resumable.

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

### 5. Long-Term Patient Memory (RAG)
The agent remembers.
*   **Context Retrieval:** Before every summary, the **Memory Agent** searches the patient's history.
*   **Continuity:** The generated summary automatically flags changes from previous visits (e.g., "Condition has improved since Jan 12").
*   **Plain-Text Storage:** Summaries are stored as plain text to keep chat/RAG results readable.

### 5b. Patient History Workspace
Clinicians can browse prior visits without leaving the app.
*   **Searchable roster:** Paginated patient list with last-visit metadata and sort.
*   **Filters & timeline:** Year-to-date default range, keyword filter, timeline pills that mirror deleted/restore state.
*   **Soft delete/restore:** Visits can be hidden and restored; “Show deleted” toggles styling.
*   **Reuse vs regenerate:** Matching uploads/template/date trigger a modal to reuse the previous output or regenerate.

### 6. Quality Review (Critic Loop)
The system self-corrects.
*   **Critic Pass:** A dedicated Critic Agent reviews the summary against source notes, uploads, and patient history.
*   **Issue Detection:** Flags hallucinations, missing facts, and contradictions.
*   **Auto-Regeneration:** The summary is regenerated until it satisfies the critic criteria.

### 7. Evidence-Linked Summaries
Summaries are backed by proof.
*   **Evidence Mapping:** Key summary statements are linked to source snippets (notes, uploads, research, guidelines).
*   **External Links:** Research and guideline findings include clickable source URLs.
*   **Audit Trail:** Evidence text is stored alongside the visit memory for later recall.

### 8. User Interface Customization (Theme Toggle)
The application offers basic UI customization to enhance user experience:
*   **Theme Toggle:** Easily switch between light and dark modes to suit your preference and reduce eye strain.

---

## 🤖 The MediNotes Assistant: A Detailed Look

The centerpiece of the user experience is the **MediNotes Assistant**, an interactive chat co-pilot that provides on-demand clinical and administrative support. It is more than a simple chatbot; it is a stateful, context-aware agent.

### Core Capabilities

1.  **Proactive Patient Briefing:**
    *   **Automatic Context:** As soon as a doctor enters a patient's name in the main form (or selects one via the "Switch" button), the Assistant automatically queries the **Memory Agent**.
    *   **Immediate Insight:** If a patient history exists, the Assistant proactively provides a one-sentence summary (e.g., *"Juan was last seen on Jan 21 for a headache..."*), giving the doctor immediate context without needing to ask.

2.  **Context-Aware Q&A:**
    *   **Dual Context:** The Assistant has access to two sources of truth: the **current, in-progress consultation** (notes, uploads) and the **long-term patient history** (past visits stored in the RAG system).
    *   **Intelligent Disambiguation:** When asked a question like "What was the last prescription?", it knows to check the RAG memory. When asked, "Summarize what I just wrote," it focuses on the current session.

3.  **On-Demand Document Generation:**
    *   The Assistant can be prompted to perform tasks that extend beyond the main summary. For example:
        *   *"Draft a referral letter to a cardiologist based on this visit."*
        *   *"Create a simple list of instructions for the patient."*
        *   *"Compare the blood pressure from this visit to the last three visits."*

4.  **Application User Guide:**
    *   The Assistant is programmed with knowledge of its own capabilities. A new user can ask:
        *   *"How do I upload an audio file?"*
        *   *"What does the Premium plan include?"*
    *   This turns the chat into a dynamic, interactive help manual.

### How it Works: The Agentic Loop

The Assistant is powered by the `chat_agent.py` and follows a sophisticated loop for every user message:

1.  **State Injection:** The frontend passes the user's message history, the current `patientName`, and the current `summary` text to the `/api/chat` endpoint.
2.  **Memory Recall (RAG):** The `ChatAgent` takes the user's last message and the `patientName` and sends a query to the `MemoryAgent`. The `MemoryAgent` performs a semantic search on the vector store (`memory_db.json`) to find the most relevant historical documents.
3.  **Prompt Engineering:** The `ChatAgent` dynamically constructs a rich prompt for the LLM, including:
    *   Its core persona ("You are MediNotes Pro...").
    *   The full conversation history.
    *   The retrieved patient history from the Memory Agent.
    *   The current, in-progress summary from the main form.
4.  **LLM Generation (Streaming):** The request is sent to the designated model (e.g., Gemini 2.5), which streams the response back.
5.  **SSE Formatting:** The backend formats the response as Server-Sent Events (SSE) to handle multi-line text and ensure a smooth, real-time typing effect on the frontend.

This entire process happens in seconds, providing a seamless, conversational experience that is deeply integrated with the application's data and state.

---

## 🧠 Agentic Architecture

Unlike traditional monolithic applications, this backend is composed of specialized **AI Agents**, each responsible for a distinct domain of the clinical workflow. This "Agentic" approach allows for:

1.  **Separation of Concerns:** Each agent handles its own logic, tools, and error recovery.
2.  **Intelligent Routing:** Agents can dynamically decide which tools to use (e.g., "Should I translate this email?") based on context rather than hard-coded rules.
3.  **Resilience:** Failures in one agent (e.g., translation) can be handled gracefully with retries and fallbacks without crashing the entire request.

### Core Agents

The system is powered by eight primary agents located in `api/agent/`:

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
    *   **Quality Control:** Runs the Critic Agent after generation and regenerates until it passes review.
    *   **Evidence Linking:** Calls the Evidence Agent after generation and streams the evidence map to the UI.
*   **Pattern:** **Orchestrator Pipeline**. It acts as a controller that manages the flow of data between sub-components.

#### 3. Coordinator Agent (`coordinator_agent.py`)
*   **Role:** The "planner".
*   **Capabilities:**
    *   **Intent Recognition:** Reads the generated summary to identify implicit tasks.
    *   **Structured Output:** Converts unstructured text (e.g., "See patient in 2 weeks") into structured JSON data (e.g., `{"type": "schedule", "date": "2025-02-14"}`).
*   **Pattern:** **Extractor**. It runs as a post-processing step to turn text into data.

#### 4. Memory Agent (`memory_agent.py`)
*   **Role:** The "hippocampus".
*   **Capabilities:**
    *   **RAG (Retrieval-Augmented Generation):** Stores summaries, original notes, and evidence links in a vector database (`vector_store.py`).
    *   **Recall:** Retrieves relevant past summaries for the current patient to provide historical context to the LLM.
*   **Pattern:** **State Manager**. It maintains long-term persistence across sessions.

#### 5. Research Agent (`research_agent.py`)
*   **Role:** The "safety checker".
*   **Capabilities:**
    *   **MCP Integration:** Uses the Brave MCP server (via `npx @brave/brave-search-mcp-server --transport stdio`) for web retrieval.
    *   **Drug Interaction Checks:** `check_drug_interactions(medications)` runs when two or more medications are detected.
    *   **Guideline Lookup:** `search_medical_guidelines(condition)` runs when the summary flow infers a relevant condition.
    *   **Summary Injection:** Findings are injected into the summary prompt to generate a **Clinical Safety Note** and **Guideline Note** in the Assessment/Plan.
    *   **Concise Output:** Returns short findings with source URLs for evidence linking.
*   **Pattern:** **Tool-Backed Researcher**. It delegates retrieval to MCP tools and summarizes results via the LLM.

#### 6. Critic Agent (`critic_agent.py`)
*   **Role:** The "Medical Director" ensuring clinical quality and accuracy.
*   **Capabilities:**
    *   **Review:** Compares the generated summary against all source materials (notes, uploads, patient history, and research findings).
    *   **Issue Extraction:** Returns a structured list of issues (hallucinations, missing facts, contradictions) along with a quality score.
    *   **Two-Step Regeneration Process:**
        1.  **Initial Draft & Review:** A single summary is generated and reviewed. If it passes, the process ends.
        2.  **Parallel Tournament:** If the initial draft fails, the agent triggers a "Best-of-N" tournament (N=5). It generates five new candidates in parallel, critiques them all, and selects the highest-scoring summary, ensuring both speed and quality.
*   **Pattern:** **Reviewer + Tournament Regenerator**. This pattern is more efficient than a simple loop, as it only escalates to a more expensive parallel generation when the first attempt fails.

#### 7. Evidence Agent (`evidence_agent.py`)
*   **Role:** The "Auditor" responsible for grounding the summary in verifiable facts.
*   **Capabilities:**
    *   **Sentence Analysis:** Breaks the final, plain-text summary into individual clinical sentences, filtering out headings and boilerplate.
    *   **Evidence Mapping:** For each meaningful sentence, it searches all source text chunks (from notes, uploads, research, etc.) to find the single best piece of supporting evidence.
    *   **Snippet Generation:** Extracts a direct quote from the source chunk to serve as a snippet.
    *   **URL Propagation:** If the source chunk comes from the Research or Guideline agent, it correctly attaches the source URLs to the citation, making them clickable in the UI.
*   **Pattern:** **Post-Processor & Grounding Agent**. This runs at the end of the pipeline and provides the final layer of verifiability and trust.

#### 8. Email Agent (`email_agent.py`)
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

### Model Fallback Strategy (`api/agent/utils/__init__.py`)
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

### Asynchronous Job Management & Real-time Streaming (Upstash Redis)
For handling long-running summary generation jobs and enabling real-time updates to the frontend, the system leverages Upstash Redis:
*   **Job Persistence:** Summary job states and events are stored in Redis, ensuring resilience and resumability.
*   **Real-time SSE Streaming:** Server-Sent Events (SSE) chunks are stored in Redis lists, allowing clients to receive real-time updates and seamlessly reconnect to ongoing streams.
*   **Job Deduplication:** Redis is used to track and reuse existing jobs for identical requests, optimizing resource usage.

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
*   `BRAVE_API_KEY`: For the Brave MCP research tool.
*   `RESEND_API_KEY`: For sending emails.
*   `CLERK_JWKS_URL`: For authentication.
*   `UPSTASH_REDIS_REST_URL`: The REST URL for Upstash Redis, used for job persistence and real-time streaming.
*   `UPSTASH_REDIS_REST_TOKEN`: The API token for authenticating with Upstash Redis.

Node.js (`npx`) is required at runtime to launch the Brave MCP server.

## Folder Structure

*   `api/agent/`: Contains all agent logic.
    *   `extraction_agent.py`: File/Audio/Image processing.
    *   `summary_agent.py`: Summarization logic & pipeline orchestration.
    *   `research_agent.py`: MCP-backed research and safety checks.
    *   `memory_agent.py`: Long-term patient memory (RAG).
    *   `coordinator_agent.py`: Action extraction from summaries.
    *   `email_agent.py`: Agentic router for email dispatch.
    *   `utils/`: Shared utilities (Fallback logic, Logging, HTML normalization, Templates).
    *   `models.py`: Shared Pydantic data models.
*   `api/index.py`: API Gateway/Router that delegates requests to specific agents.

# Local Docker Deployment
export $(cat .env | grep -v '^#' | xargs)

docker build \
  --build-arg NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY="$NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY" \
  --build-arg NEXT_PUBLIC_CLERK_JWT_TEMPLATE="$NEXT_PUBLIC_CLERK_JWT_TEMPLATE" \
  -t consultation-app .

 docker run -p 8000:8000 \
  -v memory_db:/app/data \
  -e CLERK_SECRET_KEY="$CLERK_SECRET_KEY" \
  -e CLERK_JWKS_URL="$CLERK_JWKS_URL" \
  -e OPENAI_API_KEY="$OPENAI_API_KEY" \
  -e RESEND_API_KEY="$RESEND_API_KEY" \
  -e GEMINI_API_KEY="$GEMINI_API_KEY" \
  -e GEMINI_API_URL="$GEMINI_API_URL" \
  -e BRAVE_API_KEY="$BRAVE_API_KEY" \
  -e DEEPSEEK_API_URL="$DEEPSEEK_API_URL" \
  -e DEEPSEEK_API_KEY="$DEEPSEEK_API_KEY" \
  -e NEXT_PUBLIC_CLERK_JWT_TEMPLATE="$NEXT_PUBLIC_CLERK_JWT_TEMPLATE" \
  consultation-app 

## AWS DEPLOYMENT ECR

# aws configure

Enter:

AWS Access Key ID: (paste your key)
AWS Secret Access Key: (paste your secret)
Default region: Choose based on your location:
US East Coast: us-east-1 (N. Virginia)
US West Coast: us-west-2 (Oregon)
Europe: eu-west-1 (Ireland)
Asia: ap-southeast-1 (Singapore)
Pick the closest region for best performance!
Default output format: json
Important: Remember your region choice


# 1. Authenticate Docker to ECR (using your .env values!)
aws ecr get-login-password --region $DEFAULT_AWS_REGION | docker login --username AWS --password-stdin $AWS_ACCOUNT_ID.dkr.ecr.$DEFAULT_AWS_REGION.amazonaws.com

docker build --platform linux/amd64 \
  --build-arg NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY="$NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY" \
  --build-arg NEXT_PUBLIC_CLERK_JWT_TEMPLATE="$NEXT_PUBLIC_CLERK_JWT_TEMPLATE" \
  -t consultation-app .

# 3. Tag your image (using your .env values!)
docker tag consultation-app:latest $AWS_ACCOUNT_ID.dkr.ecr.$DEFAULT_AWS_REGION.amazonaws.com/consultation-app:latest

# 4. Push to ECR
docker push $AWS_ACCOUNT_ID.dkr.ecr.$DEFAULT_AWS_REGION.amazonaws.com/consultation-app:latest
