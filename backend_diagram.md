```mermaid
graph TD
    %% User Inputs
    UserInput[User Input: Notes, Audio, Documents, Images] --> A1(ExtractionAgent: build_visit_context)

    %% Core Pipeline Orchestration (Summary Agent)
    subgraph Summary Agent (Orchestrator)
        S_start(Start Summary Pipeline) --> S1(SummaryAgent: run_summary_pipeline)
        S1 --> S2(SummaryAgent: start_summary_job)
        S2 -- job_id --> Frontend[Frontend UI]
        S2 --> S3(SummaryAgent: generate_summary_stream)
    end

    %% Extraction Phase
    S1 -->|Calls build_visit_context(visit, client)| A1
    A1 -->|Calls extract_uploaded_texts(visit)| A2[ExtractionAgent: extract_uploaded_texts]
    A1 -->|Calls extract_audio_transcripts(visit, client)| A3[ExtractionAgent: extract_audio_transcripts]
    A1 -->|Calls extract_image_texts(visit, client)| A4[ExtractionAgent: extract_image_texts]
    A1 -->|Calls extract_doctor_info(combined_text, client)| A5[ExtractionAgent: extract_doctor_info]
    A2 -- text, filename --> A1
    A3 -- text, filename --> A1
    A4 -- text, filename --> A1
    A5 -- doctor_info --> S1
    A1 -- context --> S3

    %% Memory Recall Phase
    S1 -->|Calls recall_patient_history(patient_name, query, client)| M1(MemoryAgent: recall_patient_history)
    M1 -- patient_history --> S3

    %% Initial Generation & Tool Calling
    S3 --> S4(LLM Call: Initial Summary Draft)
    S4 -- May call tools --> R1(ResearchAgent: check_drug_interactions)
    S4 -- May call tools --> R2(ResearchAgent: search_medical_guidelines)
    S4 -- May call tools --> C1(CoordinatorAgent: extract_actions)
    R1 -- research_findings --> S3
    R2 -- guideline_findings --> S3
    C1 -- actions --> S3
    S3 -- raw_text --> S5(SummaryAgent: finalize_summary_html)
    S5 -- final_html --> S6(SummaryAgent: run_summary_pipeline continues)

    %% Critic Review & Regeneration Loop
    S6 -->|Calls review_summary(final_html, source_text, ...)| CR1(CriticAgent: review_summary)
    CR1 -- review_results --> S7{Review Requires Regen?}
    S7 -- Yes --> S8(LLM Call: Regeneration Tournament)
    S8 -->|Calls review_summary on candidates| CR2(CriticAgent: review_summary)
    CR2 -- best_candidate --> S6
    S7 -- No --> S9(Continue with final_html)

    %% Post-Generation Processing
    S9 -->|Implicit: Fill doctor_info from summary| S_doc_info(ExtractionAgent: _fill_doctor_info_from_summary)
    S9 -->|If not already called: extract_actions(final_html)| C1_re(CoordinatorAgent: extract_actions)
    C1_re -- actions --> S_meta(Emit Metadata & Actions)

    S_meta -->|Calls build_evidence_map(final_html, context, client)| E1(EvidenceAgent: build_evidence_map)
    E1 -- evidence_map --> E2(EvidenceAgent: _shrink_evidence_map)
    E2 -- shrunk_evidence_map --> S_evidence(Emit Evidence Update)

    S_evidence -->|Calls remember_visit(summary, patient_name, date, ...)| M2(MemoryAgent: remember_visit)
    M2 --> S_final(Emit Final Summary)

    S_final --> S_end(End Summary Pipeline)

    %% Email Agent Interaction
    Frontend[Frontend UI] -- Email Request --> EM1(EmailAgent: run_email_agent)
    EM1 -- if language != 'English' --> EMT(EmailAgent: tool_translate_email)
    EMT -- translated_html --> EMS(EmailAgent: tool_send_email_final)
    EM1 -- if language == 'English' --> EMS
    EMS --> EmailProvider[Resend API]

    %% Chat Agent Interaction
    Frontend -- Chat Message --> CH1(ChatAgent: run_chat_agent)
    CH1 -->|Calls recall_patient_history(patient_name, query, client)| M1_chat(MemoryAgent: recall_patient_history)
    M1_chat -- memory_context --> CH1
    CH1 --> CH2(LLM Call: Chat Response)
    CH2 -- streaming_response --> Frontend

    %% Utility Modules (Implicitly used by many agents)
    subgraph Shared Utilities
        Utils_Log(utils/__init__.py: get_logger)
        Utils_Fallback_Gen(utils/__init__.py: generate_with_fallback)
        Utils_Fallback_Stream(utils/__init__.py: generate_stream_with_fallback)
        Utils_HTML(utils/html_sections.py: html_to_text, ensure_html_summary, ...)
        Utils_Upstash(utils/upstash_rest.py: UpstashRest, get_upstash)
        Utils_Guardrails(utils/guardrails.py: record_critic_issues, get_guardrails)
        Utils_Providers(utils/provider_clients.py: client_for_model, get_gemini_client, ...)
        Utils_Templates(utils/templates.py: get_template)
        Utils_Evidence(utils/evidence.py: split_sentences, chunk_text, build_source_chunks)
    end

    Utils_Fallback_Gen -.-> LLM[Various LLM Services]
    Utils_Fallback_Stream -.-> LLM
    Utils_Providers -.-> LLM

    S3 -.-> Utils_Fallback_Gen
    S3 -.-> Utils_Fallback_Stream
    CR1 -.-> Utils_Fallback_Gen
    CR2 -.-> Utils_Fallback_Gen
    E1 -.-> Utils_Fallback_Gen
    CH1 -.-> Utils_Fallback_Stream
    EM1 -.-> Utils_Fallback_Gen
    EMT -.-> Utils_Fallback_Gen
    Utils_HTML -.-> S5
    Utils_HTML -.-> E1
    Utils_Upstash -.-> S2
    Utils_Upstash -.-> S_stream_job(SummaryAgent: stream_summary_job)
    Utils_Guardrails -.-> CR1
    Utils_Guardrails -.-> CR2
    Utils_Templates -.-> S3
    Utils_Evidence -.-> E1
```