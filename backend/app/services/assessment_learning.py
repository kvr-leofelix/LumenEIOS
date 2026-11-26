"""Materialise only explicit educator-approved drafts in existing activity structures."""
import hashlib
import json
import uuid
from fastapi import HTTPException
from backend.app.modules.learnsphere.models import LearningTopic, LearningActivity, LearningAssignment
from backend.app.models.entities import ClassSection, Student, User
from backend.app.modules.learnsphere.access import require_class


async def assign_automatic_learning(db, result, completion):
    """One genuine assignment per source/kind; never create responses/completions."""
    section = await db.get(ClassSection, result.class_id)
    student = await db.get(Student, result.student_id)
    if not section or not student or (student.school_id,student.class_id)!=(result.school_id,result.class_id) or section.school_id!=result.school_id or result.subject_id not in (section.subject_ids_json or []):
        return []
    actor = await db.get(User, section.class_teacher_id) if section.class_teacher_id else None
    if not actor:
        return []
    try:
        await require_class(db, actor, result.class_id)
    except HTTPException:
        return []
    links=[]
    for draft in completion.get("learning_drafts", []):
        if draft["kind"] not in {"teach_back","mission"}:
            continue
        signature=hashlib.sha256(("automatic-assessment:"+result.id+":"+draft["kind"]).encode()).hexdigest()
        assignment_id=str(uuid.uuid5(uuid.NAMESPACE_URL,signature))
        existing=await db.get(LearningAssignment,assignment_id)
        if existing:
            links.append({"kind":draft["kind"],"assignment_id":existing.id})
            continue
        topic_ids={o.get("topic_id") for o in completion["outcomes"] if o["position"] in draft["positions"] and o.get("topic_id")}
        topic=await db.get(LearningTopic,next(iter(topic_ids))) if len(topic_ids)==1 else None
        if topic and (topic.school_id,topic.class_id,topic.subject_id)!=(result.school_id,result.class_id,result.subject_id):
            topic=None
        analysed = {m["position"]:m.get("label") for m in completion.get("competency_mappings", [])}
        if analysed:
            competency = next((analysed[p] for p in draft["positions"] if analysed.get(p)), None)
            if competency is None:
                continue
        else:
            competency=next(o["competency"] for o in completion["outcomes"] if o["position"]==draft["positions"][0])
        instructions="\n\n".join((draft["scenario"],draft["instructions"],"Submit: "+draft["expected_submission"],"Learning objective: "+draft["objective"]))
        activity=LearningActivity(id=str(uuid.uuid5(uuid.NAMESPACE_URL,"activity:"+signature)),
            topic_id=topic.id if topic else None,kind=draft["kind"],title=draft["title"],instructions=instructions,
            rubric=draft["rubric"],competency=competency,stage=draft["stage"],created_by=actor.id)
        db.add(activity)
        await db.flush()
        assignment=LearningAssignment(id=assignment_id,activity_id=activity.id,student_id=result.student_id,
            school_id=result.school_id,assigned_by=actor.id,request_key=signature,
            snapshot={"id":activity.id,"topic_id":activity.topic_id,"topic_title":topic.title if topic else "Topic unmapped",
                "kind":activity.kind,"title":activity.title,"instructions":instructions,"rubric":activity.rubric,
                "competency":competency,"stage":activity.stage,"version":1,"class_id":result.class_id,
                "subject_id":result.subject_id,"assessment_result_id":result.id,"assessment_id":result.assessment_id,
                "evidence_positions":draft["positions"],"generation":"automatic_provisional"})
        db.add(assignment)
        await db.flush()
        links.append({"kind":draft["kind"],"assignment_id":assignment.id})
    return links


async def approve_learning_plan(db, user, result, decisions, outcomes):
    output = []
    positions = {q["position"] for q in result.questions_json}
    for decision in decisions:
        item = decision.model_dump()
        if not set(item["positions"]) <= positions or len(set(item["positions"])) != len(item["positions"]):
            raise HTTPException(422, "Learning content must reference actual assessment questions once each.")
        if decision.topic_id:
            topic = await db.get(LearningTopic, decision.topic_id)
            if not topic or (topic.school_id,topic.class_id,topic.subject_id)!=(result.school_id,result.class_id,result.subject_id):
                raise HTTPException(422, "Choose an existing verified topic in this assessment's class and subject.")
        if decision.decision == "approved":
            if not decision.topic_id and decision.kind != "support":
                raise HTTPException(422, "Map a verified topic before approving a challenge or mission assignment.")
            auto_signature=hashlib.sha256(("automatic-assessment:"+result.id+":"+decision.kind).encode()).hexdigest()
            automatic=await db.get(LearningAssignment,str(uuid.uuid5(uuid.NAMESPACE_URL,auto_signature)))
            if automatic:
                item.update(activity_id=automatic.activity_id,assignment_id=automatic.id)
                output.append(item)
                continue
            if decision.topic_id:
                signature = hashlib.sha256(json.dumps([result.id,item], sort_keys=True).encode()).hexdigest()
                assignment_id = str(uuid.uuid5(uuid.NAMESPACE_URL, "assessment-learning-assignment:"+signature))
                assignment = await db.get(LearningAssignment, assignment_id)
                if not assignment:
                    activity_id = str(uuid.uuid5(uuid.NAMESPACE_URL, "assessment-learning-activity:"+signature))
                    competency = next(o["competency"] for o in outcomes if o["position"]==item["positions"][0])
                    instructions = "\n\n".join((item["scenario"],item["instructions"],"Submit: "+item["expected_submission"],"Learning objective: "+item["objective"]))
                    activity = LearningActivity(id=activity_id,topic_id=decision.topic_id,kind=decision.kind,
                        title=decision.title,instructions=instructions,rubric=decision.rubric,
                        competency=competency,stage=decision.stage,created_by=user.id)
                    db.add(activity)
                    await db.flush()
                    assignment = LearningAssignment(id=assignment_id,activity_id=activity.id,student_id=result.student_id,
                        school_id=result.school_id,assigned_by=user.id,request_key=signature,
                        snapshot={"id":activity.id,"topic_id":decision.topic_id,"topic_title":topic.title,
                            "kind":decision.kind,"title":decision.title,"instructions":instructions,
                            "rubric":decision.rubric,"competency":competency,"stage":decision.stage,"version":1,
                            "class_id":result.class_id,"subject_id":result.subject_id,
                            "assessment_result_id":result.id,"assessment_id":result.assessment_id,
                            "evidence_positions":decision.positions})
                    db.add(assignment)
                item.update(activity_id=assignment.activity_id,assignment_id=assignment.id)
        output.append(item)
    return output
