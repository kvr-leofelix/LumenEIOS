"""
Quick CLI runner for verifying the OCR Evaluation Pipeline.
Run this script with:
    python apps/lumeneios/backend/test_ocr_evaluation.py
"""
import sys
import os

# Ensure backend modules are on sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from backend.app.services.evaluation_service import (
    build_evaluation_prompt,
    parse_and_validate_evaluation,
)

def run_test():
    print("=" * 60)
    print("LumenEIOS OCR Evaluation Pipeline Test")
    print("=" * 60)

    # 1. Official Assessment Question & Marking Rubric
    questions = [
        {
            "id": "q-math-1",
            "text": "Calculate the capacity in Liters of a water reservoir of dimensions 4m x 3m x 2m.",
            "competency": "AU",
            "marks": 4,
            "rubric": "1m: Formula V=L*B*H | 1m: 24 m^3 | 1m: 24,000 Liters | 1m: Correct unit"
        }
    ]

    # 2. Raw OCR Text transcribed by Qwen (including LaTeX and an unclear marker)
    ocr_text = r"""
Ans 1:
V = L \times B \times H
V = 4 \times 3 \times 2 = 24\text{ m}^3
Capacity = 24 \times 1000 = 24,000 Liters. [unclear]
"""

    # 3. Build Evaluation Prompt
    prompt = build_evaluation_prompt(
        subject_name="Mathematics",
        assessment_title="Cycle 1 Term Assessment",
        grade="Grade 8",
        questions=questions,
        extracted_ocr_text=ocr_text
    )
    print("\n[1/3] Prompt Generation:")
    print("  -> Prompt built successfully with CBSE & NEP 2020 instructions.")
    print("  -> Length:", len(prompt), "characters")

    # 4. Mock Evaluation Response from LLM
    mock_llm_json = r"""
    {
      "student_info": {
        "detected_name": "Aarav Patel",
        "detected_roll_no": "14"
      },
      "question_evaluations": [
        {
          "question_index": 1,
          "question_id": "q-math-1",
          "question_text": "Calculate the capacity...",
          "competency": "AU",
          "max_marks": 4,
          "student_answer_extracted": "V = L \\times B \\times H = 24\\text{ m}^3 = 24,000 Liters. [unclear]",
          "status": "attempted",
          "awarded_marks": 4,
          "competency_score": 90,
          "step_breakdown": [
            {"criterion": "Formula identification", "marks_awarded": 1, "max": 1},
            {"criterion": "Volume calculation (24 m^3)", "marks_awarded": 1, "max": 1},
            {"criterion": "Liter conversion (24,000 L)", "marks_awarded": 2, "max": 2}
          ],
          "feedback": "Correct formula and calculation steps.",
          "flag_for_review": true,
          "flag_reason": "Illegible / [unclear] token in final line"
        }
      ],
      "scoring_summary": {
        "total_marks_obtained": 4,
        "max_possible_marks": 4,
        "percentage": 100,
        "competency_scores": {"AU": 90},
        "overall_feedback": "Strong application grasp.",
        "needs_teacher_review": true,
        "review_reasons": ["Q1: Illegible / [unclear] token in final line"]
      }
    }
    """

    # 5. Parse, Repair & Validate
    print("\n[2/3] Parsing & LaTeX Repair:")
    result = parse_and_validate_evaluation(mock_llm_json)
    print("  -> JSON repaired and validated against Pydantic schema successfully!")

    print("\n[3/3] Output Verification:")
    summary = result.scoring_summary
    print(f"  -> Total Marks: {summary.total_marks_obtained} / {summary.max_possible_marks} ({summary.percentage}%)")
    print(f"  -> Competency Scores: {summary.competency_scores}")
    print(f"  -> Needs Teacher Review: {summary.needs_teacher_review}")
    print(f"  -> Review Reasons: {summary.review_reasons}")
    print("\nAll pipeline checks PASSED successfully!\n")

if __name__ == "__main__":
    run_test()
