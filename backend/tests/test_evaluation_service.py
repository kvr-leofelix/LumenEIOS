import json
import unittest
import sys
import os

current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, "..", ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from backend.app.services.evaluation_service import (
    repair_json_latex,
    parse_and_validate_evaluation,
    parse_and_validate_answer_key,
    build_evaluation_prompt,
    build_answer_key_prompt,
    GRADING_SYSTEM_PROMPT,
    ANSWER_KEY_SYSTEM_PROMPT,
)


class TestEvaluationService(unittest.TestCase):

    def test_repair_json_with_latex_formulas(self):
        """Test that unescaped LaTeX backslashes inside JSON strings are repaired."""
        raw_llm_output = r'''
        ```json
        {
          "formula": "Formula $V = L \times B \times H$ stated",
          "calc": "Calculation $4 \times 3 \times 2 = 24\text{ m}^3$",
          "fraction": "\frac{1}{2}\pi r^2 h",
          "greek": "\alpha + \beta = \gamma",
          "misc": "\sqrt{x} \pm \sigma",
          "underline": "\underline{Final Result}"
        }
        ```
        '''
        repaired = repair_json_latex(raw_llm_output)
        data = json.loads(repaired)

        self.assertIn("formula", data)
        self.assertEqual(data["formula"], r"Formula $V = L \times B \times H$ stated")
        self.assertEqual(data["calc"], r"Calculation $4 \times 3 \times 2 = 24\text{ m}^3$")
        self.assertEqual(data["fraction"], r"\frac{1}{2}\pi r^2 h")
        self.assertEqual(data["greek"], r"\alpha + \beta = \gamma")
        self.assertEqual(data["misc"], r"\sqrt{x} \pm \sigma")
        self.assertEqual(data["underline"], r"\underline{Final Result}")

    def test_repair_preserves_legitimate_json_escapes(self):
        """Ensure \n, \t, \", and \\ that are genuine JSON escapes are preserved."""
        raw = r'''
        {
          "message": "Line 1\nLine 2\tTabbed",
          "quote": "She said \"Correct!\"",
          "escaped_slash": "C:\\Program Files\\App"
        }
        '''
        repaired = repair_json_latex(raw)
        data = json.loads(repaired)

        self.assertEqual(data["message"], "Line 1\nLine 2\tTabbed")
        self.assertEqual(data["quote"], 'She said "Correct!"')
        self.assertEqual(data["escaped_slash"], "C:\\Program Files\\App")

    def test_repair_removes_trailing_commas(self):
        """Ensure trailing commas in arrays and objects are cleaned."""
        raw = r'''
        {
          "items": [
            {"name": "item1", },
            {"name": "item2", },
          ],
          "count": 2,
        }
        '''
        repaired = repair_json_latex(raw)
        data = json.loads(repaired)
        self.assertEqual(len(data["items"]), 2)
        self.assertEqual(data["count"], 2)

    def test_repair_strips_preamble_and_markdown(self):
        """Ensure conversational preamble and postamble around JSON are removed."""
        raw = r'''
        Here is the evaluation result for the student submission:
        ```json
        {
          "status": "success",
          "score": 85
        }
        ```
        Hope this helps the teacher!
        '''
        repaired = repair_json_latex(raw)
        data = json.loads(repaired)
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["score"], 85)

    def test_parse_full_evaluation_schema_with_latex(self):
        """Test parsing complete student evaluation output with embedded LaTeX."""
        raw = r'''
        ```json
        {
          "student_info": {
            "detected_name": "Aarav Sharma",
            "detected_roll_no": "14"
          },
          "question_evaluations": [
            {
              "question_index": 1,
              "question_id": "q1",
              "question_text": "Calculate the volume of a 4m x 3m x 2m tank.",
              "competency": "AU",
              "max_marks": 4,
              "student_answer_extracted": "$V = L \times B \times H = 4 \times 3 \times 2 = 24\text{ m}^3$",
              "status": "attempted",
              "awarded_marks": 3,
              "competency_score": 75,
              "step_breakdown": [
                {"criterion": "Formula $V = L \times B \times H$ stated", "marks_awarded": 1, "max": 1},
                {"criterion": "Calculation $4 \times 3 \times 2 = 24\text{ m}^3$", "marks_awarded": 1, "max": 1},
                {"criterion": "Conversion to 24,000 Liters", "marks_awarded": 1, "max": 1},
                {"criterion": "Time calculation with correct units", "marks_awarded": 0, "max": 1}
              ],
              "feedback": "Volume and conversion correct; final time calculation missing.",
              "flag_for_review": false,
              "flag_reason": null
            }
          ],
          "scoring_summary": {
            "total_marks_obtained": 3,
            "max_possible_marks": 4,
            "percentage": 75,
            "competency_scores": {
              "AU": 75
            },
            "overall_feedback": "Good application skills.",
            "needs_teacher_review": false,
            "review_reasons": []
          }
        }
        ```
        '''
        eval_result = parse_and_validate_evaluation(raw)
        # Verify access
        self.assertIsNotNone(eval_result)
        dump = eval_result.model_dump()
        self.assertEqual(dump["student_info"]["detected_name"], "Aarav Sharma")
        self.assertEqual(len(dump["question_evaluations"]), 1)
        self.assertEqual(dump["question_evaluations"][0]["awarded_marks"], 3)
        self.assertIn(r"\times", dump["question_evaluations"][0]["student_answer_extracted"])

    def test_parse_answer_key_generation(self):
        """Test parsing answer key generation response."""
        raw = r'''
        ```json
        {
          "subject": "Mathematics",
          "generated_answer_key": [
            {
              "question_index": 1,
              "question_id": "q1",
              "question_text": "Calculate cylinder volume with radius 7m, height 10m.",
              "competency": "AU",
              "max_marks": 4,
              "model_solution": "$V = \pi r^2 h = \frac{22}{7} \times 49 \times 10 = 1540\text{ m}^3$",
              "marking_rubric": [
                {"criterion": "Formula $V = \pi r^2 h$", "marks": 1},
                {"criterion": "Substitution $\frac{22}{7} \times 49 \times 10$", "marks": 2},
                {"criterion": "Final answer $1540\text{ m}^3$", "marks": 1}
              ],
              "essential_keywords": ["volume", "pi", "cubic meters"]
            }
          ]
        }
        ```
        '''
        ak_result = parse_and_validate_answer_key(raw)
        self.assertIsNotNone(ak_result)
        dump = ak_result.model_dump()
        self.assertEqual(dump["subject"], "Mathematics")
        self.assertEqual(len(dump["generated_answer_key"]), 1)
        self.assertEqual(dump["generated_answer_key"][0]["max_marks"], 4)

    def test_build_evaluation_prompt(self):
        """Test prompt builder generates valid prompt string with context."""
        questions = [
            {
                "id": "q1",
                "text": "Calculate the volume of a 4m x 3m x 2m cuboid tank.",
                "marks": 4,
                "competency": "AU",
            }
        ]
        ocr_text = "Ans 1: V = L * B * H = 4 * 3 * 2 = 24 m^3. [unclear] liters."
        prompt = build_evaluation_prompt(
            subject_name="Mathematics",
            assessment_title="Cycle 1 Assessment",
            grade="Grade 8",
            questions=questions,
            extracted_ocr_text=ocr_text,
        )

        self.assertIn("Subject: Mathematics", prompt)
        self.assertIn("Grade 8", prompt)
        self.assertIn("Ans 1: V = L * B * H", prompt)
        self.assertIn("CRITICAL LATEX ESCAPING IN JSON", prompt)
        self.assertIn("HUMAN-IN-THE-LOOP SAFETY INVARIANT", prompt)

    def test_build_answer_key_prompt(self):
        """Test prompt builder for answer key generation."""
        questions = [
            {
                "id": "q1",
                "text": "Explain why 0 has no reciprocal.",
                "marks": 3,
            }
        ]
        prompt = build_answer_key_prompt(
            subject_name="Mathematics",
            grade="Grade 8",
            questions_without_key=questions,
        )

        self.assertIn("Subject: Mathematics", prompt)
        self.assertIn("Explain why 0 has no reciprocal", prompt)
        self.assertIn("generated_answer_key", prompt)
        self.assertIn("marking_rubric", prompt)


if __name__ == "__main__":
    unittest.main()
