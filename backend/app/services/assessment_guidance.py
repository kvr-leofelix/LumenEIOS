"""Read-only, assessment-scoped support; generation only runs on submission/review/retry."""
import copy
from datetime import timezone
from fastapi import HTTPException
from sqlalchemy import select
from backend.app.models.entities import Assessment, Subject
from backend.app.modules.learnsphere.access import require_student, require_class
from backend.app.modules.learnsphere.assessment_models import AssessmentResultRecord
from backend.app.services.assessment_results import accessible_result
from backend.app.services.panchapadi import automatic_outcomes, provisional_view, student_evaluation, saved_question_guidance, reviewed_stage_view


TEACHER_MAGNET_ACTIVITY = "Create a simple experiment where students can observe the attraction of various materials to a magnet. Materials such as iron, steel, and aluminum can be used. Discuss the results and relate them to the concept of magnetic materials."
MAGNET_PRACTICE_QUESTION = "Which of the following materials is most likely to be a magnetic material? A) Wood, B) Iron, C) Plastic, D) Copper. Explain your choice."


def guidance_for_role(advice,role,seen=None):
    if advice is None:return None
    public=copy.deepcopy(advice)
    activity=public.get("activity") or ""
    # Restrict the specified teacher-led experiment, including its older saved
    # wording. Do not rewrite either stored version or unrelated student tasks.
    teacher_activity=activity.startswith("Create a simple experiment where students can observe the attraction of ")
    if teacher_activity:
        public["activity_for_student"]=True
        if role not in {"teacher","principal"}:
            public["activity"]=None
    if public.get("practice_question")==MAGNET_PRACTICE_QUESTION:
        public["practice_for_student"]=True
    if seen is not None:
        for field,target in (("activity",teacher_activity),("practice_question",public.get("practice_for_student"))):
            value=public.get(field)
            if target and value:
                if value in seen:public[field]=None
                else:seen.add(value)
    return public


async def student_assessments(db,user,student_id):
    student=await require_student(db,user,student_id)
    rows=(await db.execute(select(AssessmentResultRecord,Assessment,Subject)
        .join(Assessment,Assessment.id==AssessmentResultRecord.assessment_id)
        .join(Subject,Subject.id==AssessmentResultRecord.subject_id)
        .where(AssessmentResultRecord.student_id==student.id,AssessmentResultRecord.school_id==student.school_id,
            Assessment.school_id==student.school_id,Assessment.class_id==AssessmentResultRecord.class_id,
            Assessment.subject_id==AssessmentResultRecord.subject_id)
        .order_by(AssessmentResultRecord.submitted_at,AssessmentResultRecord.id))).all()
    output=[]
    for record,assessment,subject in rows:
        if user.role in {"admin","principal","teacher"}:
            try:await require_class(db,user,record.class_id)
            except HTTPException:continue
        output.append({"assessment_id":assessment.id,"result_id":record.id,"name":assessment.title,
            "subject":subject.name,"subject_id":subject.id,"date":assessment.date,
            "submitted_at":record.submitted_at.replace(tzinfo=timezone.utc).isoformat() if record.submitted_at.tzinfo is None else record.submitted_at.isoformat()})
    return output


async def question_guidance(db,user,student_id,assessment_id):
    await require_student(db,user,student_id)
    record=await db.scalar(select(AssessmentResultRecord).where(AssessmentResultRecord.student_id==student_id,
        AssessmentResultRecord.assessment_id==assessment_id))
    if not record:raise HTTPException(404,"No submitted assessment is available in this student's scope.")
    record,assessment,_=await accessible_result(db,user,record.id)
    educator=user.role in {"teacher","principal","admin"}
    if educator:await require_class(db,user,record.class_id)
    review=record.reviews_json[-1] if record.reviews_json else None
    attempts=(record.panchapadi_json or {}).get("attempts",[])
    last=attempts[-1] if attempts else {}
    guidance=saved_question_guidance(record)
    outcomes=review["outcomes"] if review else automatic_outcomes(record)
    evaluation=reviewed_stage_view(record)
    evaluation=evaluation or provisional_view(record)
    from backend.app.modules.learnsphere.automation import current_competencies
    competencies = {m["position"]: m for m in current_competencies(record)}
    items=[]
    seen=set()
    for q in record.questions_json:
        position=q["position"];o=next(o for o in outcomes if o["position"]==position)
        answer=next(a for a in record.answers_json if a["position"]==position)
        actual=answer.get("answer_text")
        if actual is None:
            index=answer.get("selected_option_index")
            actual=q["options"][index] if type(index) is int and 0<=index<len(q["options"]) else None
        advice=guidance_for_role(guidance.get(position),user.role,seen)
        status="Unassessed" if o.get("score") is None else "Correct" if o["score"]==o["maximum"] else "Incorrect" if o["score"]==0 else "Partially correct"
        stages=[s["stage"] for s in evaluation["stages"] if any(c["position"]==position for c in s["contributions"])]
        mapping = competencies[position]
        if not educator:
            mapping = {k:v for k,v in mapping.items() if k in {"position","label","confidence","status"}}
            mapping["reason"] = ("The teacher reviewed this question's competency." if mapping["status"].startswith("teacher_")
                else "Competency analysis is provisional; uncertain mappings need teacher review.")
        items.append({"position":position,"text":q["text"],"answer":actual,"score":o.get("score"),"maximum":o["maximum"],
            "status":status,"competency":competencies[position]["label"] or "Unmapped","stages":stages,
            "competency_mapping":mapping, "stored_competency":q["competency"] if educator else None,
            "concept_evidence":o.get("concept_evidence") if educator else None,
            "correct_answer":q.get("correct_answer") if educator or (review and o.get("key_verified")) else None,
            "feedback":o.get("feedback") if review or educator else None,"guidance":advice,
            "missing_information":None if advice else "Guidance is being generated automatically. Temporary failures are retried; saved responses and reviewed marks remain unchanged."})
    concept_stages = []
    for score in evaluation["stages"]:
        groups = {"demonstrated": [], "partial": [], "missing": []}
        for contribution in score["contributions"]:
            position = contribution["position"]
            if not contribution["eligible"]:
                continue
            concept = guidance.get(position, {}).get("expected_concept")
            if not concept:
                continue
            state = "demonstrated" if contribution["score"] == contribution["maximum"] else "missing" if contribution["score"] == 0 else "partial"
            groups[state].append({"position": position, "concept": concept,
                "marks_status": "teacher_confirmed" if evaluation.get("teacher_verified") else "provisional",
                "description_status": "provisional_ai"})
        concept_stages.append({"stage": score["stage"], **groups})
    subject=await db.get(Subject,record.subject_id)
    return {"automation_version":len((record.panchapadi_json or {}).get("competency_reviews", [])), "concept_stages":concept_stages, "assessment_id":assessment.id,"result_id":record.id,"student_id":student_id,"name":assessment.title,
        "subject":subject.name if subject else record.subject_id,"date":assessment.date,
        "evaluation_status":"teacher_reviewed" if review else "provisional","guidance_status":"provisional" if len(guidance)==len(record.questions_json) else "running" if last.get("status")=="running" else "pending",
        "questions":items,"performance":{"result_id":record.id,"assessment_id":assessment.id,"assessment_name":assessment.title,
            "subject_id":record.subject_id,"assessed_at":record.submitted_at.isoformat(),"evaluation":student_evaluation(evaluation),
            "learning_plan":[{k:v for k,v in item.items() if k!="rubric"} for item in (review or {}).get("learning_plan",[]) if item.get("decision")=="approved"]},
        "warnings":last.get("evaluation_warnings",[])}
