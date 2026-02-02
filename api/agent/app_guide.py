APP_GUIDE = """
MediNotes App Guide

Purpose
- MediNotes helps clinicians capture consultations, generate structured summaries, review patient history, and send patient-ready emails.

Main Areas
- Consultation Documentation: create a visit, upload files, generate summary, review actions, and send email.
  - Example: Enter Juan Dela Cruz, select today’s date, paste notes, upload a prescription photo, then click Generate Summary.
- MediNotes Assistant: chat for patient-specific Q&A and app guidance.
  - Example: Ask “Summarize Juan’s last visit” or “What does Date of Visit do?”
- Patient History (Longitudinal View): filter and browse prior visits.
  - Example: Select a patient, set From=2026-01-01 and To=2026-12-31, then open a visit from the timeline.

Consultation Documentation Fields
- Patient Name: identifies which patient context to use for summary and chat.
  - Example: “Maria Cruz” ensures memory recall and chat context target Maria’s records.
- Date of Visit: date tied to the generated summary and memory entry.
  - Example: Set 2026-02-01 so this summary is stored under that visit date.
- Template: summary format style used for output structure.
  - Example: Pick a template for your clinic style before generating.
- Consultation Notes: primary clinical text input for the visit.
  - Example: “BP 150/95, headache x3 days, started Paracetamol PRN.”
- Supporting Files:
  - Consultation File: PDF, DOCX, TXT, MD
    - Example: Upload `follow_up_notes.pdf` to include prior details.
  - Prescription Image: PNG, JPG, WEBP
    - Example: Upload `rx_photo.jpg` to extract medication names and doses.
  - Audio Upload: MP3, M4A, WAV, WEBM, OGG
    - Example: Upload `consult_audio.m4a` to transcribe spoken findings.

How Summary Generation Works
- User enters notes and optional uploads, then clicks Generate Summary.
- Example: Notes + one PDF + one image, then click Generate Summary.
- System extracts text from uploads (document/audio/image) and merges context.
- Example: Prescription image text is converted to readable medication lines.
- Memory retrieves relevant prior visit context for the selected patient.
- Example: Prior visit on 2026-01-21 is added as historical context.
- Summary is generated in structured sections, then reviewed by critic for quality.
- Example: If critic flags missing facts, summary is regenerated automatically.
- Clinical decision support can add medication safety and guideline notes.
- Example: Interaction check appears when multiple meds are detected.
- Evidence links are attached to supported statements when available.
- Example: “ECG normal” links to the exact upload snippet.
- Suggested Next Actions are extracted from the summary.
- Example: “Follow-up in 4 weeks” appears as an action card.

Patient History (Memory)
- MediNotes stores visit outputs in memory and retrieves relevant prior visits during summary and chat.
- Example: Asking “How was last month’s BP?” recalls prior visit summaries.
- You can ask for longitudinal context, prior findings, or changes over time.
- Example: “Compare chest pain trend across last 3 visits.”
- If no relevant history exists, MediNotes reports that no history is available.
- Example: New patient with no prior visits returns “No past history found.”

Patient History View (Timeline, Date Range, Filters)
- Patient selector: choose the patient to load visit history.
- Example: Select “Juan Dela Cruz” from dropdown.
- Date range (From/To): narrows visits by visit date window.
- Example: From 2026-01-01 to 2026-03-01 to view Q1 visits only.
- Keyword search: filters visit list by matching content.
- Example: Search “dizziness” to find related visits.
- Sort: newest-first or oldest-first ordering.
- Example: Switch to oldest-first to review progression from first visit.
- Timeline pills: quick visual visit navigation by date.
- Example: Click pill “2026-01-23” to jump to that visit.
- Load more: pagination for additional visits.
- Example: Click Load more to fetch older records.
- Show deleted: reveal soft-deleted visits, with restore flow.
- Example: Toggle Show deleted, then click Restore on a removed visit.

Email Workflow
- Use Send Email card after summary generation.
- Example: Open Send Email once summary appears.
- Fill/confirm patient email and doctor/clinic details.
- Example: Set patient email and confirm doctor name/clinic before send.
- Optional language translation is supported before sending.
- Example: Select Filipino to translate patient instructions.
- Sending uses clinic-branded formatting from the generated patient email section.
- Example: Email header shows clinic branding and doctor signature block.

MediNotes Assistant Scope
- Can answer:
  - Patient-specific clinical questions grounded in current summary + retrieved history.
    - Example: “What meds is the patient currently taking?”
  - App usage questions (fields, uploads, history filters, timeline, workflow).
    - Example: “What does date range do in Patient History?”
- Cannot answer:
  - General unrelated questions outside patient context and app features.
    - Example: “Who won the game last night?” is out of scope.

Limits
- For patient-specific clinical answers, MediNotes answers only from current summary and retrieved patient history.
- For non-clinical, non-app questions, MediNotes should state it is limited to patient-specific clinical questions and app features.
""".strip()
