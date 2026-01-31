# MediNotes Premium — User Guide

This guide explains how to use the web app to review and manage patient visits, generate summaries, and work with the assistant.

## 1) Access and layout
- Sign in: Use the sign-in button (Clerk). After login, click **Go to App**.
- Main areas:
  - **Consultation** tab: Upload notes/audio, pick a template, generate a summary, actions, and evidence.
  - **Patient History** tab: Search/select a patient, browse timelines, filter, sort, and view past visits. (Chat stays available.)
  - **MediNotes Assistant**: Floating chat panel available across tabs.

## 2) Selecting a patient
- Open **Patient History**.
- Use the patient dropdown to search by name; it supports text search and “load more” to fetch additional patients.
- Renaming: Use the rename control to edit the displayed patient name (only in the history context).

## 3) Timeline and grouped visit list
- Timeline pills (newest first): VISIT_SUMMARY, VISIT_NOTES, VISIT_EVIDENCE. Click a pill to load that visit in the details panel.
- Timeline is horizontally scrollable; drag or use the scrollbar.
- Grouped cards by date: Each date block shows visit type badges, timestamp, template label, and quick actions (View details, Evidence, Delete/Restore, Copy summary).

## 4) Filtering, sorting, pagination
- Date range defaults: Jan 1 of the current year through today; adjust **From/To** calendars.
- Sort toggle: Newest ↔ Oldest; applies to both timeline and list.
- Keyword filter: Filters within the current patient’s visits (server-side search).
- Pagination: Visits load in batches (default 10). Click **Load more** to fetch the next page (rate‑limited). An empty state appears if filters hide everything.

## 5) Viewing a visit
- Click **View details** or a timeline pill to open the full visit panel.
- Panel shows type, date, timestamp, template, body content, and buttons:
  - **Return to list**: Back to grouped list.
  - **Copy summary**: Copies the current summary text.
  - **Delete / Restore**: Soft delete or bring back the visit.
- Evidence section: If available, shows linked snippets; “Copy with citations” is provided where enabled.

## 6) Soft delete and restore
- Soft delete hides a visit from counts and default view.
- **Show deleted** toggle: When on, deleted cards appear tinted with a **Deleted** badge and a **Restore** button.
- Counts and pagination exclude deleted items unless “Show deleted” is enabled.

## 7) Regeneration vs reuse (cache-aware prompt)
- When you re-run a summary with the same patient, date, template, notes, and attachments:
  - A modal asks to **Reuse previous output** (load cached summary/actions/evidence) or **Regenerate** (run model again).
- If inputs differ (notes, template, files), regeneration runs automatically.

## 8) Consultation tab workflow (current visit)
- Upload files (PDF/DOCX/TXT), paste text, or add audio (transcribed to English).
- Choose a template (e.g., SOAP, Med Review).
- Click **Generate**: Produces visit summary, actions, and evidence.
- Copy actions/summary as needed; results are stored to Patient History with timestamp.

## 9) Sorting and timestamps
- All saved visits include date and time; sorting uses both.
- Timestamps are shown on visit cards and detail panels.

## 10) Pagination + search interactions
- “Load more” respects current filters and sort.
- Keyword search and date filters constrain pagination results; clearing filters resets the list before the next load.

## 11) Safety and undo
- Soft delete is reversible; use **Restore** when “Show deleted” is on.
- Regeneration never overwrites soft-deleted rows; restored items reappear in counts and timeline.

## 12) Tips
- Use date filters to narrow a patient with many visits before searching by keyword.
- If you expect cached reuse but see regeneration, check that notes/files/template match exactly.
- Keep “Show deleted” off for cleaner reading; toggle it only when you need to restore.


