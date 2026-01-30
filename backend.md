# Backend API Documentation: Agentic Healthcare SaaS

This document provides a detailed overview of the backend API architecture, focusing on the specialized AI agents that drive the application's functionality. The system is built around a multi-agent paradigm, where each agent is responsible for distinct aspects of clinical workflow automation.

## Architectural Overview

The backend employs a Hub-and-Spoke agentic pattern, orchestrated by the Summary Agent, with various worker agents performing specialized tasks. This design incorporates Reflection (Critic Loop), Retrieval-Augmented Generation (RAG), and Autonomous Routing to ensure robustness, clinical accuracy, and verifiability.

## Core Agents and Their Functions

Here's a breakdown of each agent, its role, and key functions it implements, including their inputs and outputs.

### 1. Summary Agent (`api/agent/summary_agent.py`)
*   **Role:** The central orchestrator and "brain" of the clinical synthesis pipeline. It manages the entire lifecycle of patient visit summaries, from coordinating diverse inputs and driving the summary generation process to integrating quality control and ensuring real-time delivery to the frontend. This agent is pivotal in ensuring that the final output is accurate, well-researched, and compliant with clinical standards.
*   **Key Implemented Functions:**
    *   `run_summary_pipeline(visit: Visit, client: AsyncOpenAI, request: Optional[Any]) -> AsyncGenerator[str, None]`
        *   **Purpose:** This is the high-level orchestrator. It manages the entire summary generation process, flowing data through various sub-agents. It handles context building, summary generation, critic review, evidence mapping, and persistence. It also incorporates caching for efficiency and checks for client disconnections to gracefully terminate long-running operations.
        *   **Inputs:**
            *   `visit` (Type: `Visit` - Pydantic model): Contains all raw patient encounter data, including notes, uploaded files (documents, audio, images), and basic patient information.
            *   `client` (Type: `AsyncOpenAI`): An asynchronous OpenAI client instance used for interacting with various LLM services (e.g., GPT models, Gemini models).
            *   `request` (Type: `Optional[Any]` - typically `fastapi.Request`): The incoming HTTP request object, used to check for client disconnection during streaming.
        *   **Outputs:**
            *   `AsyncGenerator[str, None]`: Yields Server-Sent Events (SSE) chunks (strings) in real-time. These chunks contain status updates, metadata, actions, evidence updates, and the final HTML summary.

    *   `generate_summary_stream(...)` (Internal function, called by `run_summary_pipeline`)
        *   **Purpose:** This asynchronous generator handles the core logic of summary generation. It constructs prompts, makes initial LLM calls (potentially with tool use for research and action extraction), processes tool outputs, performs a crucial critic review loop (including a parallel regeneration tournament if the initial draft fails), and finalizes the HTML output.
        *   **Inputs:** Includes `visit`, `context` (a dictionary of processed inputs and findings), `doctor_info`, `client`, and an optional `should_abort` callable.
        *   **Outputs:** `AsyncGenerator[str, None]`: Yields SSE chunks, including status messages, keep-alive signals, and intermediate/final summary content.

    *   `start_summary_job(visit: Visit, client: AsyncOpenAI) -> str`
        *   **Purpose:** Initiates (or reuses) a summary generation job. It checks if an identical job is already running or completed. **If Upstash Redis is configured (via `UPSTASH_REDIS_REST_URL` and `UPSTASH_REDIS_REST_TOKEN`), it persists job state and events for resilience and deduplication.** Otherwise, it falls back to in-memory job management.
        *   **Inputs:**
            *   `visit` (Type: `Visit`): Patient visit data.
            *   `client` (Type: `AsyncOpenAI`): OpenAI client.
        *   **Outputs:**
            *   `str`: A unique `job_id` string that can be used to stream job events.

    *   `stream_summary_job(job_id: str, request: Optional[Any]) -> AsyncGenerator[str, None]`
        *   **Purpose:** Streams Server-Sent Events (SSE) for a specific summary job ID. **If Upstash Redis is enabled, it efficiently tails the Redis list containing job events with adaptive backoff.** Otherwise, it streams events from an in-memory job object. This ensures real-time updates to the frontend and allows clients to reconnect and resume streaming from where they left off.
        *   **Inputs:**
            *   `job_id` (Type: `str`): The unique identifier for the summary job.
            *   `request` (Type: `Optional[Any]`): The HTTP request object for disconnection checks.
        *   **Outputs:**
            *   `AsyncGenerator[str, None]`: Yields SSE chunks representing status updates, intermediate results, and the final output of the summary job.

    *   `correction_prompt_for(visit: Visit, context: Dict, summary_html: str, review: Dict) -> str`
        *   **Purpose:** Constructs a specific LLM prompt designed to guide the model in revising a previously generated summary. This is used when the Critic Agent identifies issues, providing the LLM with the problematic summary, original source context, and a list of identified issues to fix.
        *   **Inputs:**
            *   `visit` (Type: `Visit`): Patient visit data.
            *   `context` (Type: `Dict`): Contains processed source data, patient history, and research findings.
            *   `summary_html` (Type: `str`): The HTML content of the summary that needs correction.
            *   `review` (Type: `Dict`): The structured output from the Critic Agent detailing the issues found.
        *   **Outputs:**
            *   `str`: A formatted string, representing the user-role content for an LLM call, instructing it to correct the summary.

    *   `finalize_summary_html(client: AsyncOpenAI, template: Dict, raw_text_or_html: str) -> str`
        *   **Purpose:** Guarantees that the final HTML output for the summary strictly adheres to the required three-section structure (`summary`, `next_steps`, `patient_email`). It attempts multiple repair strategies, including stripping non-conforming content, using a normalization wrapper, and even an LLM-based repair pass, to ensure the output is consistent and valid.
        *   **Inputs:**
            *   `client` (Type: `AsyncOpenAI`): OpenAI client for potential LLM-based repair.
            *   `template` (Type: `Dict`): The structural template for the summary.
            *   `raw_text_or_html` (Type: `str`): The raw text or HTML content generated by the LLM, which may or may not conform to the strict structure.
        *   **Outputs:**
            *   `str`: A strictly formatted HTML string containing only the three required sections.

    *   `_strip_tool_call_artifacts(text: str) -> str`
        *   **Purpose:** An internal utility function to clean up raw text generated by LLMs by removing specific tool call markup (e.g., DSML tags) that might be inadvertently included in the model's output.
        *   **Inputs:**
            *   `text` (Type: `str`): The raw text content from an LLM response.
        *   **Outputs:**
            *   `str`: The cleaned text with tool call artifacts removed.

### 2. Extraction Agent (`api/agent/extraction_agent.py`)
*   **Role:** The "senses" of the system. This agent is responsible for the initial ingestion, decoding, and processing of various unstructured medical data inputs provided by the user. It transforms raw files (audio, images, documents) and notes into structured or plain-text formats suitable for further agentic processing.
*   **Key Implemented Functions:**
    *   `build_visit_context(visit: Visit, client: AsyncOpenAI) -> Dict[str, Any]`
        *   **Purpose:** This is the primary function for gathering all available input data related to a patient visit. It orchestrates calls to other extraction functions to process uploaded documents, audio recordings, and prescription images, combines them with raw notes, and extracts initial doctor information. The output is a consolidated dictionary representing the comprehensive context of the visit.
        *   **Inputs:**
            *   `visit` (Type: `Visit`): A Pydantic model containing all raw input data for the current patient visit (e.g., `notes`, `uploaded_files`, `audio_files`, `image_files`).
            *   `client` (Type: `AsyncOpenAI`): An asynchronous OpenAI client, used for audio transcription and image text extraction.
        *   **Outputs:**
            *   `Dict[str, Any]`: A dictionary containing:
                *   `notes_text` (str): Cleaned doctor's notes.
                *   `attachments` (List[Tuple[str, str]]): List of (label, text) for all processed uploaded files (documents, audio transcripts, image texts).
                *   `combined_text` (str): A single string containing all textual context for the visit.
                *   `prescription_text` (str), `prescription_filename` (str), `prescription_texts` (List[str]), `prescription_filenames` (List[str]): Extracted prescription details.

    *   `extract_uploaded_texts(visit: Visit) -> List[Tuple[str, str]]`
        *   **Purpose:** Decodes and extracts plain text from various document types uploaded by the user. It supports PDF, DOCX, and plain text files, ensuring that their content is made available for LLM processing. It also handles error conditions for unsupported formats or unreadable files.
        *   **Inputs:**
            *   `visit` (Type: `Visit`): Contains `uploaded_files` (list of `Base64File` objects) and legacy file fields.
        *   **Outputs:**
            *   `List[Tuple[str, str]]`: A list of tuples, where each tuple contains the extracted text content (`str`) and the original filename (`str`).

    *   `extract_audio_transcripts(visit: Visit, client: AsyncOpenAI) -> List[Tuple[str, str]]`
        *   **Purpose:** Transcribes audio recordings of patient consultations into English text. It leverages OpenAI's Whisper model to convert speech to text, making the audio content accessible for analysis by other agents. Includes validation for file size and supported audio formats.
        *   **Inputs:**
            *   `visit` (Type: `Visit`): Contains `audio_files` (list of `Base64File` objects) and legacy audio fields.
            *   `client` (Type: `AsyncOpenAI`): OpenAI client for Whisper API.
        *   **Outputs:**
            *   `List[Tuple[str, str]]`: A list of tuples, each containing the transcribed text (`str`) and the original audio filename (`str`).

    *   `extract_image_texts(visit: Visit, client: AsyncOpenAI) -> List[Tuple[str, str]]`
        *   **Purpose:** Processes uploaded images, primarily targeting handwritten prescription images, to extract and translate their textual content into English. It uses a vision-enabled LLM (like GPT-4o Vision) to interpret the image and format the extracted prescription details.
        *   **Inputs:**
            *   `visit` (Type: `Visit`): Contains `image_files` (list of `Base64File` objects) and legacy image fields.
            *   `client` (Type: `AsyncOpenAI`): OpenAI client for vision model API.
        *   **Outputs:**
            *   `List[Tuple[str, str]]`: A list of tuples, each containing the extracted prescription text (`str`) and the original image filename (`str`).

    *   `extract_doctor_info(source_text: str, client: AsyncOpenAI) -> Dict[str, str]`
        *   **Purpose:** Identifies and extracts key contact and identification details of the doctor and patient from a given `source_text`. This includes doctor's name, phone, clinic, email, and patient's name and email. It uses an LLM to perform this entity extraction in a structured JSON format and then validates the extracted information against the original source to prevent hallucinations.
        *   **Inputs:**
            *   `source_text` (Type: `str`): A combined string of all textual content available for the visit (notes, transcripts, documents).
            *   `client` (Type: `AsyncOpenAI`): OpenAI client for LLM-based extraction.
        *   **Outputs:**
            *   `Dict[str, str]`: A dictionary with keys like `doctor_name`, `doctor_phone`, `clinic_name`, `doctor_email`, `patient_name`, `patient_email`, and their corresponding extracted string values (empty string if not found or validated).

### 3. Research Agent (`api/agent/research_agent.py`)
*   **Role:** The "safety checker" and external knowledge retriever. This agent proactively fetches crucial medical data from the web to validate safety, provide clinical guidelines, and augment the context for summary generation, ensuring that the summaries are not only accurate but also clinically sound and up-to-date.
*   **Key Implemented Functions:**
    *   `check_drug_interactions(medications: List[str]) -> List[Dict[str, Any]]`
        *   **Purpose:** Takes a list of medication names and performs a web search to identify any potential drug-drug interactions. The findings are summarized concisely, along with their source URLs, to be incorporated into the clinical summary as a "Clinical Safety Note."
        *   **Inputs:**
            *   `medications` (Type: `List[str]`): A list of medication names detected in the patient's notes or prescriptions.
        *   **Outputs:**
            *   `List[Dict[str, Any]]`: A list of dictionaries, where each dictionary contains a `summary` (str) of the interaction findings and a `sources` (list of dicts with `title`, `url`) list for verification. Returns an empty list if no interactions are found or if fewer than two medications are provided.

    *   `search_medical_guidelines(condition: str) -> List[Dict[str, Any]]`
        *   **Purpose:** Given a clinical condition, this function searches for relevant medical guideline recommendations from authoritative sources. The goal is to provide evidence-based support that can be integrated into the patient's assessment and plan within the summary.
        *   **Inputs:**
            *   `condition` (Type: `str`): The clinical condition or diagnosis to research.
        *   **Outputs:**
            *   `List[Dict[str, Any]]`: A list of dictionaries, each containing a `summary` (str) of the guideline recommendations and a `sources` (list of dicts with `title`, `url`) list. Returns an empty list if no relevant guidelines are found or if the condition is empty.

    *   `_run_research_request(request: str, instructions: str) -> List[Dict[str, Any]]` (Internal utility)
        *   **Purpose:** A generic internal function that orchestrates a web search request using an MCP (Model Context Protocol) server (specifically Brave Search). It constructs an agent, sends the query, processes the results, and handles caching to prevent redundant API calls for common queries.
        *   **Inputs:**
            *   `request` (Type: `str`): The specific query string for the web search.
            *   `instructions` (Type: `str`): System-level instructions for the research agent, guiding it on how to perform the search and format the output.
        *   **Outputs:**
            *   `List[Dict[str, Any]]`: A list of dictionaries, each representing a research finding with keys like `summary` and `sources` (containing `title` and `url`).

### 4. Critic Agent (`api/agent/critic_agent.py`)
*   **Role:** The "Medical Director" within the system. This agent is dedicated to ensuring the clinical quality, factual accuracy, and safety of generated summaries through a rigorous reflection loop. It acts as a gatekeeper, preventing erroneous or incomplete information from reaching the user or patient.
*   **Key Implemented Functions:**
    *   `review_summary(summary_html: str, source_text: str, patient_history: str, research_findings: str, guideline_findings: str, client: AsyncOpenAI) -> Dict[str, Any]`
        *   **Purpose:** This is the core review function. It performs a comprehensive comparison of the generated `summary_html` against all available source materials: the original `source_text` (notes, uploads), `patient_history`, and any `research_findings` or `guideline_findings`. It identifies critical issues such as hallucinations, omissions of important facts, contradictions, and missing safety information.
        *   **Inputs:**
            *   `summary_html` (Type: `str`): The HTML content of the clinical summary to be reviewed.
            *   `source_text` (Type: `str`): The combined raw text from all initial inputs (doctor's notes, transcribed audio, extracted document text).
            *   `patient_history` (Type: `str`): Relevant past medical history retrieved from the Memory Agent.
            *   `research_findings` (Type: `str`): Formatted output from the Research Agent regarding drug interactions.
            *   `guideline_findings` (Type: `str`): Formatted output from the Research Agent regarding medical guidelines.
            *   `client` (Type: `AsyncOpenAI`): An asynchronous OpenAI client for making LLM calls for the review process.
        *   **Outputs:**
            *   `Dict[str, Any]`: A dictionary containing the review results:
                *   `score` (float): A quality score between 0.0 and 1.0, indicating the summary's adherence to accuracy and safety.
                *   `needs_fix` (bool): A flag indicating if the summary requires regeneration.
                *   `issues` (List[str]): A list of general issues found.
                *   `missing` (List[str]): A list of critical information omitted from the summary.
                *   `hallucinations` (List[str]): A list of invented or unsubstantiated facts.

    *   `review_requires_regen(review: Dict[str, Any]) -> bool`
        *   **Purpose:** A utility function that determines, based on the `review` dictionary provided by `review_summary`, whether the summary needs to undergo a regeneration process. This is triggered if critical issues (hallucinations, missing info) are found, general issues exist, or the overall `score` falls below a predefined threshold.
        *   **Inputs:**
            *   `review` (Type: `Dict[str, Any]`): The structured review result from `review_summary`.
        *   **Outputs:**
            *   `bool`: `True` if the summary requires regeneration, `False` otherwise.

    *   `format_issue_lines(review: Dict[str, Any]) -> List[str]`
        *   **Purpose:** Converts the structured issues within a `review` dictionary into a list of human-readable string lines. This is useful for displaying feedback to the user or for constructing prompts for the Summary Agent during regeneration.
        *   **Inputs:**
            *   `review` (Type: `Dict[str, Any]`): The structured review result.
        *   **Outputs:**
            *   `List[str]`: A list of strings, each representing an identified issue or type of issue (e.g., "hallucinations: Patient reported X, but source says Y").

### 5. Evidence Agent (`api/agent/evidence_agent.py`)
*   **Role:** The "Auditor" of the system. This agent is crucial for grounding the generated clinical summary in verifiable facts, enhancing trust and explainability. It creates a transparent link between each statement in the summary and its supporting source documents.
*   **Key Implemented Functions:**
    *   `build_evidence_map(summary_html: str, context: Dict[str, Any], client: AsyncOpenAI) -> Dict[str, Any]`
        *   **Purpose:** This is the primary function for constructing the comprehensive evidence map. It first processes the `summary_html` to extract individual meaningful sentences. Concurrently, it builds a collection of `source chunks` from all available inputs in the `context` (notes, uploads, research findings, etc.). An LLM is then used to semantically map each summary sentence to the single best supporting source chunk. Finally, it generates concise evidence snippets and propagates source URLs.
        *   **Inputs:**
            *   `summary_html` (Type: `str`): The final HTML content of the generated clinical summary.
            *   `context` (Type: `Dict[str, Any]`): The comprehensive visit context, including `notes_text`, `attachments`, `patient_history`, `research_findings`, and `guideline_findings`.
            *   `client` (Type: `AsyncOpenAI`): An asynchronous OpenAI client for the LLM mapping process.
        *   **Outputs:**
            *   `Dict[str, Any]`: A dictionary representing the evidence map, containing:
                *   `chunks` (List[Dict]): A list of all source text chunks, including their `id`, `text`, `source` type, and any `sources` (URLs).
                *   `citations` (List[Dict]): A list of citation objects. Each citation links a `sentence` from the summary to one or more `chunk_ids` and provides `snippets` (exact quotes from the chunks).

    *   `_shrink_evidence_map(evidence_map: Dict[str, Any]) -> Dict[str, Any]` (Internal utility)
        *   **Purpose:** Optimizes the size of the `evidence_map` payload, particularly for storage or transmission. It truncates the number of chunks and citations to a predefined maximum and shortens long evidence snippets, ensuring the payload remains manageable while retaining essential information.
        *   **Inputs:**
            *   `evidence_map` (Type: `Dict[str, Any]`): The raw evidence map generated by `build_evidence_map`.
        *   **Outputs:**
            *   `Dict[str, Any]`: A reduced and optimized version of the evidence map.

### 6. Memory Agent (`api/agent/memory_agent.py`)
*   **Role:** The "hippocampus" of the system. This agent provides crucial long-term persistence for patient data and enables Retrieval-Augmented Generation (RAG). It stores key visit information and can semantically retrieve relevant past history to enrich current consultations or chat interactions.
*   **Key Implemented Functions:**
    *   `remember_visit(summary: str, patient_name: str, date: str, client: AsyncOpenAI, doc_type: str = "visit_summary") -> None`
        *   **Purpose:** Stores generated clinical summaries, original visit notes, or evidence links into a vector database. This function ensures that valuable patient data is preserved across sessions and can be retrieved later to provide historical context.
        *   **Inputs:**
            *   `summary` (Type: `str`): The textual content (summary, notes, or evidence) to be stored.
            *   `patient_name` (Type: `str`): The name of the patient associated with the visit.
            *   `date` (Type: `str`): The date of the visit.
            *   `client` (Type: `AsyncOpenAI`): OpenAI client, used for embedding generation required by the vector store.
            *   `doc_type` (Type: `str`, default: "visit_summary"): Categorizes the type of document being stored (e.g., "visit_summary", "visit_notes", "visit_evidence").
        *   **Outputs:** `None`. The function performs a side effect of adding a document to the vector store.

    *   `recall_patient_history(patient_name: str, query: str, client: AsyncOpenAI) -> str`
        *   **Purpose:** Retrieves semantically relevant past clinical history for a specific patient. Given a `query` (typically the current consultation text or a chat message), it searches the vector database for documents related to the `patient_name` and returns the most relevant historical context formatted as a string suitable for injection into an LLM's prompt.
        *   **Inputs:**
            *   `patient_name` (Type: `str`): The name of the patient whose history is being recalled.
            *   `query` (Type: `str`): The query string (e.g., current notes, a user's question) used to find relevant past documents.
            *   `client` (Type: `AsyncOpenAI`): OpenAI client for embedding generation for the query.
        *   **Outputs:**
            *   `str`: A formatted string containing retrieved past clinical history for the patient, or a message indicating no history was found or an error occurred.

    *   `list_known_patients() -> List[str]`
        *   **Purpose:** Provides an administrative utility to list all unique patient names for whom records exist in the vector store. This helps in managing patient data and can be used for UI elements like patient selection dropdowns.
        *   **Inputs:** None.
        *   **Outputs:**
            *   `List[str]`: A sorted list of unique patient names found in the vector store.

### 7. Coordinator Agent (`api/agent/coordinator_agent.py`)
*   **Role:** The "planner" or task manager. This agent is responsible for analyzing the generated clinical summary to identify implicit future actions or next steps and then structuring these into an actionable, machine-readable format. This moves the system beyond mere summarization to proactive planning.
*   **Key Implemented Functions:**
    *   `extract_actions(summary_text: str, client: AsyncOpenAI) -> List[Dict[str, Any]]`
        *   **Purpose:** Analyzes the textual content of a clinical summary, specifically looking for phrases that imply "Next Steps" or actionable items. It then extracts these into a structured JSON format, categorizing them by `type` (e.g., `schedule`, `prescribe`, `referral`, `lab`, `other`) and providing `label` (short title) and `details` (contextual information).
        *   **Inputs:**
            *   `summary_text` (Type: `str`): The plain-text content of the clinical summary (or specifically the "Next Steps" section).
            *   `client` (Type: `AsyncOpenAI`): An asynchronous OpenAI client for LLM-based action extraction.
        *   **Outputs:**
            *   `List[Dict[str, Any]]`: A list of dictionaries, where each dictionary represents an extracted actionable item with keys like `type`, `label`, and `details`. Returns an empty list if no actions are found or an error occurs.

### 8. Email Agent (`api/agent/email_agent.py`)
*   **Role:** The "dispatcher." This agent handles patient communication delivery, acting as an autonomous router that intelligently decides on the necessary steps (e.g., translation) before sending an email. It demonstrates dynamic tool use within an agentic loop.
*   **Key Implemented Functions:**
    *   `run_email_agent(payload: EmailPayload, client: AsyncOpenAI) -> Dict[str, Any]`
        *   **Purpose:** This is the main entry point for sending emails. It receives a structured payload containing email details (recipient, subject, HTML content, language, clinic info). Using an agent loop, it dynamically decides if the email needs translation based on the `language` field. It then calls the `translate_email` tool (if needed) and subsequently the `send_email_final` tool to dispatch the email.
        *   **Inputs:**
            *   `payload` (Type: `EmailPayload` - Pydantic model): A structured object containing email details such as `to`, `subject`, `html`, `reply_to`, `clinic_name`, and `language`.
            *   `client` (Type: `AsyncOpenAI`): OpenAI client for agentic decision-making and tool calls.
        *   **Outputs:**
            *   `Dict[str, Any]`: A dictionary indicating the status of the email dispatch (e.g., `{"status": "sent", "id": "..."}`). Raises `HTTPException` on failure.

    *   `tool_translate_email(client: AsyncOpenAI, *, html: str, language: str) -> str`
        *   **Purpose:** A tool function designed to translate the visible text content within an HTML email into a specified target language. It preserves all HTML tags, attributes, links, and proper nouns, ensuring the email's structure and functionality remain intact while localizing the content.
        *   **Inputs:**
            *   `client` (Type: `AsyncOpenAI`): OpenAI client for translation.
            *   `html` (Type: `str`): The HTML content of the email to be translated.
            *   `language` (Type: `str`): The target language for the translation (e.g., "Spanish", "French").
        *   **Outputs:**
            *   `str`: The translated HTML content.

    *   `tool_send_email_final(*, to: str, subject: str, html: str, reply_to: str, clinic_name: str) -> Dict[str, Any]`
        *   **Purpose:** A tool function responsible for dispatching the final email using the Resend API. It constructs the `From` header with the clinic's name and sends the translated (or original) HTML content to the specified recipient.
        *   **Inputs:**
            *   `to` (Type: `str`): The recipient's email address.
            *   `subject` (Type: `str`): The subject line of the email.
            *   `html` (Type: `str`): The HTML body of the email.
            *   `reply_to` (Type: `str`): The email address for replies.
            *   `clinic_name` (Type: `str`): The name of the clinic to be used in the sender's display name.
        *   **Outputs:**
            *   `Dict[str, Any]`: A dictionary containing the sending status and an email ID (e.g., `{"status": "sent", "id": "re_..."}`). Raises `HTTPException` if the Resend API key is missing or the sending fails.

### 9. Chat Agent (`api/agent/chat_agent.py`)
*   **Role:** The interactive "Clinical Co-pilot." This agent provides on-demand clinical and administrative support to doctors through a conversational interface. It is stateful and context-aware, leveraging current consultation data and long-term patient history to provide accurate and relevant answers.
*   **Key Implemented Functions:**
    *   `run_chat_agent(history: List[Dict[str, str]], patient_name: str, current_summary: str, client: AsyncOpenAI) -> AsyncGenerator[str, None]`
        *   **Purpose:** Manages the interactive chat session with the doctor. For each user message, it first queries the Memory Agent to retrieve relevant past patient history. It then dynamically constructs a rich LLM prompt that includes its persona, the full conversation history, the retrieved patient history, and the current in-progress summary. Finally, it streams the LLM's response back to the user in real-time.
        *   **Inputs:**
            *   `history` (Type: `List[Dict[str, str]]`): A list of dictionaries representing the full conversation history between the user and the assistant.
            *   `patient_name` (Type: `str`): The name of the patient currently in context.
            *   `current_summary` (Type: `str`): The text of the current, in-progress consultation summary.
            *   `client` (Type: `AsyncOpenAI`): An asynchronous OpenAI client for interacting with the LLM (e.g., Gemini).
        *   **Outputs:**
            *   `AsyncGenerator[str, None]`: Yields Server-Sent Events (SSE) chunks (strings), representing the streaming response from the LLM, enabling a real-time typing effect in the UI.

## Shared Utilities (`api/agent/utils`)

The `utils` directory contains a collection of shared helper functions and modules used across various agents. These utilities provide common functionalities such as logging, model fallback strategies, text processing, HTML manipulation, client management for different LLM providers, and external service integrations.

### `__init__.py`
*   **Purpose:** This file initializes the `utils` package, sets up global logging, and, most importantly, provides the core logic for the **Model Fallback Strategy** used by all agents. This strategy ensures resilience by automatically retrying with less expensive or alternative models if a primary model fails or is unavailable.
*   **Key Implemented Functions:**
    *   `get_logger(name: str) -> logging.Logger`
        *   **Purpose:** Returns a configured `logging.Logger` instance for a given name, ensuring consistent logging across the application.
        *   **Inputs:**
            *   `name` (Type: `str`): The name of the logger (typically `__name__` of the calling module).
        *   **Outputs:**
            *   `logging.Logger`: A logger instance.

    *   `generate_with_fallback(client: AsyncOpenAI, messages: List[Dict[str, Any]], models: Optional[List[str]] = None, max_retries: int = 1, **kwargs) -> Any`
        *   **Purpose:** Executes an LLM completion request with a cascading fallback strategy. If the primary model fails, it automatically retries with a sequence of fallback models (e.g., `gpt-5-nano`, `gpt-4o-mini`, `gpt-3.5-turbo`) to enhance reliability and availability. It also handles client selection for different OpenAI-compatible providers.
        *   **Inputs:**
            *   `client` (Type: `AsyncOpenAI`): The default asynchronous OpenAI client.
            *   `messages` (Type: `List[Dict[str, Any]]`): The conversation messages to send to the LLM.
            *   `models` (Type: `Optional[List[str]]`): A list of model names to try, in order of preference. Defaults to `DEFAULT_MODEL_CHAIN`.
            *   `max_retries` (Type: `int`): Maximum retries per model in the chain. Defaults to 1.
            *   `**kwargs`: Additional keyword arguments passed directly to `client.chat.completions.create`.
        *   **Outputs:**
            *   `Any`: The response object from the successful LLM completion (e.g., `ChatCompletion` object).
            *   **Raises:** An exception if all models in the fallback chain fail.

    *   `generate_stream_with_fallback(client: AsyncOpenAI, messages: List[Dict[str, Any]], models: Optional[List[str]] = None, max_retries: int = 1, **kwargs) -> Any`
        *   **Purpose:** Attempts to establish an LLM streaming response using the same cascading fallback strategy as `generate_with_fallback`. It aims to return an asynchronous generator of chunks, ensuring that if a model fails to *initiate* the stream, a fallback is attempted. Once a stream is established, it's assumed successful for the duration of the connection.
        *   **Inputs:** (Same as `generate_with_fallback`, plus `stream=True` is automatically added in kwargs).
        *   **Outputs:**
            *   `Any`: An asynchronous generator that yields streaming chunks from the successful LLM response.
            *   **Falls back to:** Yielding a friendly error message as a stream if all models fail to establish a stream.

### `evidence.py`
*   **Purpose:** Provides core utilities for text processing, such as sentence splitting and text chunking, specifically designed to prepare source content for the Evidence Agent's mapping process. It helps break down large texts into manageable, semantically coherent units.
*   **Key Implemented Functions:**
    *   `normalize_whitespace(text: str) -> str`
        *   **Purpose:** Standardizes whitespace in a given text by replacing various newline characters with `\n`, trimming lines, and collapsing multiple blank lines into single ones. This ensures consistent text formatting for subsequent processing.
        *   **Inputs:**
            *   `text` (Type: `str`): The input text string.
        *   **Outputs:**
            *   `str`: The text with normalized whitespace.

    *   `split_sentences(text: str) -> List[str]`
        *   **Purpose:** Splits a block of text into individual sentences while attempting to handle common abbreviations correctly (e.g., "Dr. Smith" should not split after "Dr."). It normalizes whitespace before splitting.
        *   **Inputs:**
            *   `text` (Type: `str`): The input text block.
        *   **Outputs:**
            *   `List[str]`: A list of strings, where each string is a sentence.

    *   `chunk_text(text: str, max_chars: int = 500) -> List[str]`
        *   **Purpose:** Divides a long text into smaller, overlapping (implicitly, by sentence boundary) chunks, suitable for vector embedding or LLM context windows. It attempts to chunk by paragraphs and then by sentences, ensuring no chunk exceeds `max_chars`.
        *   **Inputs:**
            *   `text` (Type: `str`): The input text to chunk.
            *   `max_chars` (Type: `int`): The maximum character length for each chunk. Defaults to 500.
        *   **Outputs:**
            *   `List[str]`: A list of text chunks.

    *   `build_source_chunks(context: Dict[str, Any], max_chars: int = 500) -> List[Dict[str, Any]]`
        *   **Purpose:** Aggregates and chunks all relevant textual content from the `context` (doctor's notes, uploaded documents, patient history, research findings, guideline findings) into a unified list of source chunks. Each chunk is assigned a unique ID, source type, and label, along with any associated URLs, making it ready for evidence mapping.
        *   **Inputs:**
            *   `context` (Type: `Dict[str, Any]`): The comprehensive visit context, including all textual inputs.
            *   `max_chars` (Type: `int`): Maximum character length for each generated chunk. Defaults to 500.
        *   **Outputs:**
            *   `List[Dict[str, Any]]`: A list of dictionaries, each representing a source chunk with keys like `id`, `source`, `label`, `text`, and `sources` (list of URLs).

### `guardrails.py`
*   **Purpose:** Manages dynamic guardrails for LLM output formatting and structure. It observes issues reported by the Critic Agent, learns common structural problems, rewrites them into neutral rules, and persists these rules to a JSON file. These guardrails are then injected into system prompts to guide LLMs towards more compliant output.
*   **Key Implemented Functions:**
    *   `get_guardrails() -> List[str]`
        *   **Purpose:** Retrieves the currently active list of guardrail rules from the persistent storage (`data/critic_guardrails.json`).
        *   **Inputs:** None.
        *   **Outputs:**
            *   `List[str]`: A list of string rules (guardrails).

    *   `record_critic_issues(issues: List[str], client: AsyncOpenAI, repeat_threshold: int = ..., max_guardrails: int = ...) -> List[str]`
        *   **Purpose:** Processes a list of `issues` identified by the Critic Agent. It tracks the frequency of each issue. If an issue repeats beyond a `repeat_threshold`, it calls `_rewrite_issue` to transform it into a generic formatting guardrail and adds it to the active guardrails list, up to `max_guardrails`. This allows the system to dynamically learn and enforce desired output structures.
        *   **Inputs:**
            *   `issues` (Type: `List[str]`): A list of issue descriptions from the Critic Agent.
            *   `client` (Type: `AsyncOpenAI`): OpenAI client for rewriting issues into guardrails.
            *   `repeat_threshold` (Type: `int`): How many times an issue must appear before being considered for promotion to a guardrail. Defaults to 3.
            *   `max_guardrails` (Type: `int`): Maximum number of guardrails to maintain. Defaults to 8.
        *   **Outputs:**
            *   `List[str]`: The updated list of active guardrail rules.

    *   `_rewrite_issue(issue: str, client: AsyncOpenAI) -> str` (Internal utility)
        *   **Purpose:** Uses an LLM to rephrase a specific `issue` (e.g., a factual error) into a neutral, short, and actionable formatting or structural rule. Clinical or patient-specific issues are filtered out, as guardrails should be general rules for LLM behavior.
        *   **Inputs:**
            *   `issue` (Type: `str`): The specific issue string from the Critic Agent.
            *   `client` (Type: `AsyncOpenAI`): OpenAI client for the rewriting LLM call.
        *   **Outputs:**
            *   `str`: A rewritten guardrail rule, or an empty string if the issue is not suitable for a general rule.

### `html_sections.py`
*   **Purpose:** Provides utility functions for parsing, rendering, and validating the strict HTML section structure required for clinical summaries. It ensures that summaries consistently conform to predefined HTML sections (`summary`, `next_steps`, `patient_email`) regardless of the LLM's raw output, and handles conversion between HTML and plain text.
*   **Key Implemented Functions:**
    *   `looks_like_html(text: str) -> bool`
        *   **Purpose:** A quick check to determine if a given string `text` appears to be HTML by looking for specific HTML tags and attributes (`<section>`, `data-section="summary"`).
        *   **Inputs:**
            *   `text` (Type: `str`): The input string to check.
        *   **Outputs:**
            *   `bool`: `True` if the text looks like HTML, `False` otherwise.

    *   `split_sections(text: str) -> Dict[str, List[str]]`
        *   **Purpose:** Parses a plain-text summary (potentially markdown-like) and attempts to split it into logical sections based on predefined section headings (`SECTION_HEADINGS`). This is used for initial parsing when the LLM output is not yet strict HTML.
        *   **Inputs:**
            *   `text` (Type: `str`): The raw text content of a summary.
        *   **Outputs:**
            *   `Dict[str, List[str]]`: A dictionary where keys are section names (`summary`, `next_steps`, `patient_email`) and values are lists of text lines belonging to that section.

    *   `render_paragraphs(lines: List[str]) -> str`
        *   **Purpose:** Converts a list of text lines into HTML paragraphs (`<p>`). It groups consecutive non-empty lines into paragraphs and escapes HTML special characters.
        *   **Inputs:**
            *   `lines` (Type: `List[str]`): A list of text lines.
        *   **Outputs:**
            *   `str`: An HTML string with `<p>` tags.

    *   `render_list(lines: List[str]) -> str`
        *   **Purpose:** Converts a list of text lines into an HTML unordered list (`<ul><li>`). It strips common bullet prefixes and escapes HTML special characters.
        *   **Inputs:**
            *   `lines` (Type: `List[str]`): A list of text lines, potentially with bullet points.
        *   **Outputs:**
            *   `str`: An HTML string with `<ul>` and `<li>` tags.

    *   `render_summary_section(lines: List[str], template: Dict) -> str`
        *   **Purpose:** Renders the content of a specific summary section (e.g., "Summary of visit") into HTML, respecting sub-headings and determining whether to use paragraphs or lists based on content. It uses a `template` to define expected sub-headings.
        *   **Inputs:**
            *   `lines` (Type: `List[str]`): Text lines for a specific summary section.
            *   `template` (Type: `Dict`): The template dictionary containing `headings` for sub-sections.
        *   **Outputs:**
            *   `str`: An HTML string representing the rendered summary section.

    *   `ensure_html_summary(raw: str, template: Dict) -> str`
        *   **Purpose:** The main function to guarantee that a given raw text or HTML content is transformed into a valid, three-section HTML summary. If the input is not already structured HTML, it attempts to parse and render it. If sections are missing, it appends placeholder sections. This is critical for consistent UI rendering.
        *   **Inputs:**
            *   `raw` (Type: `str`): The raw text or HTML content from the LLM.
            *   `template` (Type: `Dict`): The template for the summary structure.
        *   **Outputs:**
            *   `str`: A fully formed HTML string containing the three required sections, with placeholders if content was missing.

    *   `html_to_text(html: str) -> str`
        *   **Purpose:** Converts HTML content back into clean, readable plain text. It intelligently handles various HTML tags (like `<br>`, `<p>`, `<li>`, section tags) by inserting appropriate newlines, strips all other tags, and unescapes HTML entities. This is useful for memory storage or further text-based processing.
        *   **Inputs:**
            *   `html` (Type: `str`): The input HTML string.
        *   **Outputs:**
            *   `str`: The plain text representation of the HTML.

### `provider_clients.py`
*   **Purpose:** Manages the instantiation and caching of `AsyncOpenAI` client instances for different LLM providers (e.g., DeepSeek, Gemini, default OpenAI). This allows agents to seamlessly switch between models from various providers without incurring per-request client setup overhead, crucial for the model fallback strategy.
*   **Key Implemented Functions:**
    *   `get_deepseek_client() -> Optional[AsyncOpenAI]`
        *   **Purpose:** Returns a cached `AsyncOpenAI` client configured for DeepSeek's API. It initializes the client only if the `DEEPSEEK_API_KEY` or `DEEPSEEK_API_URL` environment variables are present and have changed, or if no client is cached.
        *   **Inputs:** None (relies on environment variables).
        *   **Outputs:**
            *   `Optional[AsyncOpenAI]`: An `AsyncOpenAI` client instance for DeepSeek, or `None` if not configured.

    *   `get_gemini_client() -> Optional[AsyncOpenAI]`
        *   **Purpose:** Returns a cached `AsyncOpenAI` client configured for Gemini's OpenAI-compatible API endpoint. Similar to `get_deepseek_client`, it initializes and caches the client based on `GEMINI_API_KEY` and `GEMINI_API_URL` environment variables.
        *   **Inputs:** None (relies on environment variables).
        *   **Outputs:**
            *   `Optional[AsyncOpenAI]`: An `AsyncOpenAI` client instance for Gemini, or `None` if not configured.

    *   `client_for_model(model: str, default_client: AsyncOpenAI) -> AsyncOpenAI`
        *   **Purpose:** A dispatcher function that selects the appropriate `AsyncOpenAI` client based on the provided `model` name. If the model name contains "deepseek" or "gemini," it attempts to retrieve the cached client for that provider. Otherwise, it defaults to the `default_client` (typically the OpenAI client).
        *   **Inputs:**
            *   `model` (Type: `str`): The name of the LLM model to be used.
            *   `default_client` (Type: `AsyncOpenAI`): The default OpenAI client instance.
        *   **Outputs:**
            *   `AsyncOpenAI`: The selected `AsyncOpenAI` client instance for the given model.

### `templates.py`
*   **Purpose:** Manages predefined templates for clinical summaries. These templates define the structure and headings for different types of summaries (e.g., SOAP, Discharge, Referral), ensuring consistency in the generated output and guiding the LLM's generation process.
*   **Key Implemented Functions:**
    *   `get_template(visit: Visit) -> Dict[str, Any]`
        *   **Purpose:** Retrieves a specific summary template based on the `template_id` provided in the `Visit` object. If no `template_id` is specified or if it's not found, it defaults to a "generic" summary template. Each template includes a `label`, `headings`, and example `summary_html` to guide the LLM.
        *   **Inputs:**
            *   `visit` (Type: `Visit`): The patient visit object, which may contain a `template_id`.
        *   **Outputs:**
            *   `Dict[str, Any]`: A dictionary representing the selected summary template.

### `upstash_rest.py`
*   **Purpose:** Provides a client for interacting with the Upstash Redis REST API. This utility is critical for enabling asynchronous job management, persistence, and real-time Server-Sent Events (SSE) streaming, particularly for long-running processes like summary generation. It handles HTTP communication, retries, and error handling for Redis commands.
*   **Key Implemented Classes/Functions:**
    *   `class UpstashRest`
        *   **Purpose:** The main class for the Upstash Redis REST API client. It encapsulates the base URL, authentication token, and timeout settings for Redis operations.
        *   **`__init__(self, base_url: str, token: str, timeout_s: float = 10.0)`**
            *   **Purpose:** Initializes the Upstash REST client with the necessary connection details.
            *   **Inputs:** `base_url` (str), `token` (str), `timeout_s` (float).
            *   **Outputs:** None (initializes object).

        *   **`execute(self, command: str, *args: Any, max_retries: int = 4) -> Any`**
            *   **Purpose:** Sends a single Redis command (e.g., `HSET`, `GET`, `RPUSH`) to the Upstash Redis REST API. It handles HTTP requests, retries on transient errors (429, 5xx), and parses the `{"result": ...}` or `{"error": "..."}` response structure from Upstash.
            *   **Inputs:**
                *   `command` (Type: `str`): The Redis command (e.g., "HSET", "LRANGE").
                *   `*args` (Type: `Any`): Arguments for the Redis command.
                *   `max_retries` (Type: `int`): Maximum number of retries for transient errors. Defaults to 4.
            *   **Outputs:**
                *   `Any`: The `result` field from the Upstash response, or raises `UpstashError` on failure.

        *   **`pipeline(self, commands: List[List[Any]], max_retries: int = 4) -> Any`**
            *   **Purpose:** (Optional) Sends multiple Redis commands as a pipeline to the Upstash Redis REST API, optimizing network round trips. It expects a list of command arrays (e.g., `[["HSET",...], ["LTRIM",...]]`).
            *   **Inputs:**
                *   `commands` (Type: `List[List[Any]]`): A list of Redis command arrays to be executed in a pipeline.
                *   `max_retries` (Type: `int`): Maximum retries for transient errors. Defaults to 4.
            *   **Outputs:**
                *   `Any`: The JSON response from the Upstash pipeline endpoint, or raises `UpstashError`.

    *   `get_upstash() -> UpstashRest`
        *   **Purpose:** A singleton factory function that returns a cached `UpstashRest` client instance. It retrieves `UPSTASH_REDIS_REST_URL` and `UPSTASH_REDIS_REST_TOKEN` from environment variables. If these are missing, it raises an `UpstashError`. This ensures that only one client instance is created and reused across the application.
        *   **Inputs:** None (relies on environment variables).
        *   **Outputs:**
            *   `UpstashRest`: A configured `UpstashRest` client instance.
            *   **Raises:** `UpstashError` if environment variables are not set.

## Backend API Entry Points (`api/index.py`, `api/server.py`)

*   **`api/index.py`**: This file likely serves as the main entry point and router for the FastAPI application. It defines the HTTP endpoints (e.g., `/summary`, `/chat`, `/email`) and delegates incoming requests to the appropriate agent functions, serving as the interface between the frontend and the agentic backend.

*   **`api/server.py`**: This file is typically responsible for initializing and configuring the FastAPI application instance. It might include settings for middleware, error handling, database connections (if any outside agents), and potentially mounts the API router defined in `index.py`. It effectively starts the Uvicorn server or equivalent to serve the API.
