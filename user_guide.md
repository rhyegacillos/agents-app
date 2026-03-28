# MediNotes Premium — User Guide

This guide explains how to use the current application as it exists today, including the consultation workflow, patient history, the assistant, and the major behaviors that now depend on persisted patient memory.

## 1. Main areas of the app

The application is organized around three practical work areas:

- **Consultation**: create or update the current visit
- **Patient History**: review prior visits and evidence
- **MediNotes Assistant**: ask questions about the current visit or prior history

The assistant remains useful across the rest of the interface, but the main workflow usually starts in Consultation and then moves into History or Email as needed.

## 2. Consultation workflow

### 2.1 Provide inputs

You can build a consultation from one or more inputs:

- typed notes
- uploaded files such as PDF, DOCX, TXT, or Markdown
- audio recordings for transcription
- prescription or handwritten-note images

The system combines these into one visit context before generation starts.

### 2.2 Choose the template

Select the desired template for the summary, such as SOAP or medication-review style output. Template choice matters because it affects:

- output structure
- reuse-versus-regenerate matching
- stored visit metadata

### 2.3 Generate the summary

When you click **Generate**:

1. inputs are processed
2. patient history is recalled when available
3. the summary pipeline runs
4. progress streams back to the UI
5. the final summary, actions, and evidence become available

Because the pipeline includes extraction, research, critic review, and evidence mapping, generation can take noticeably longer than a simple one-shot prompt.

## 3. Reuse versus regenerate

The app is designed to avoid unnecessary duplicate runs.

If you attempt to generate a visit with matching:

- patient
- date
- template
- notes
- uploaded inputs

the app can prompt you to either:

- **Reuse previous output**
- **Regenerate**

### When to reuse

Reuse is appropriate when you want the prior validated result back quickly and the source material has not changed.

### When to regenerate

Regenerate is appropriate when:

- the source material changed
- you suspect the prior output is stale
- you want a fresh run with the current model behavior

## 4. Patient history workspace

The Patient History area is now backed by persistent memory rather than temporary local storage. That means prior visits are intended to remain available across redeploys.

### 4.1 Selecting a patient

You can:

- search by patient name
- page through more patients
- open a selected patient’s visit history

### 4.2 Reviewing visits

The history view supports:

- grouped visits
- timeline navigation
- date filtering
- keyword filtering
- sort order changes

### 4.3 Visit details

Opening a visit shows:

- visit type
- date and time
- summary or stored text
- evidence when available

### 4.4 Soft delete and restore

Deleting a visit is a soft delete, not a hard purge. This means:

- the visit is hidden from normal browsing
- it can be restored later
- deleted items can be shown when the relevant toggle is enabled

## 5. Evidence view

Evidence is intended to answer the question:

- “Why did the summary say this?”

When available, the evidence view shows the source snippet or reference linked to a summary statement. This is especially useful when reviewing:

- medication decisions
- safety notes
- claims derived from uploaded documents

## 6. MediNotes Assistant

The assistant is context-aware rather than generic.

It can use:

- the current consultation state
- the current summary
- prior patient memory

This means it is useful for questions such as:

- what happened at the previous visit
- what medications were previously used
- summarize the current notes
- compare current information with prior context

## 7. Email workflow

After a summary is reviewed, you can use the email path to prepare patient-facing communication.

The system can:

- draft email content
- translate it when needed
- send it through the configured email delivery path

## 8. Sorting, filtering, and pagination

The patient-history interface supports:

- date range filtering
- keyword filtering
- load-more pagination
- sort order changes

These controls work together. For example, pagination respects your current filter set rather than loading unfiltered records.

## 9. What persists and what does not

### 9.1 What persists

The following are intended to persist across redeploys:

- long-term patient memory
- patient-history documents
- stored evidence entries

### 9.2 What is temporary

The following are more operational than historical:

- in-progress streaming state
- transient summary job execution state

That distinction matters because a completed visit should remain recallable later, while a half-finished stream is not itself part of the patient record.

## 10. Practical tips

- Use patient history before regenerating a summary if you want to understand what already exists for the patient.
- Use regenerate only when the prior result is not appropriate for the current inputs.
- If the assistant seems unaware of prior history, check whether the patient name matches the stored record you expect.
- If a visit disappears unexpectedly, check whether it was soft-deleted and whether the deleted-items view is enabled.

## 11. Mental model for using the app well

The easiest way to use the app correctly is to think of it this way:

- **Consultation** is for building the current visit
- **History** is for verifying continuity across visits
- **Assistant** is for asking questions across both the current session and stored patient memory

That mental model lines up with how the backend is actually built and will produce the most predictable results in daily use.

