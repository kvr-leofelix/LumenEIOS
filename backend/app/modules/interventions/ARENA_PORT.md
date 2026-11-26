# Arena port notes

- Reuses existing `apps/lumeneios/backend/app/services/ai_gateway.py` (not replaced).
- Uses Unified Student Progress evidence/explanations for grounding.
- Assignment uses the **full Differentiated Homework** workflow
  (`assign_intervention_via_dh`: bank selection → draft → approve → assign).
  It does **not** create legacy `HomeworkRemediation` rows.
- AI bank items are opt-in (`include_ai_generated=False` by default); Gemini is not required.
- Access control reuses Differentiated Homework-linked `student_progress.access`.
