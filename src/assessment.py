from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional
import uuid


@dataclass
class AssessmentWorkflow:
    id: str
    role: str
    recruiter: str
    candidate: str
    status: str = 'created'
    evaluation: Optional[Dict[str, object]] = None


_WORKFLOWS: Dict[str, AssessmentWorkflow] = {}


def create_assessment_workflow(role: str, recruiter: str, candidate: str) -> Dict[str, object]:
    workflow = AssessmentWorkflow(
        id=str(uuid.uuid4())[:8],
        role=role,
        recruiter=recruiter,
        candidate=candidate,
    )
    _WORKFLOWS[workflow.id] = workflow
    return {
        'id': workflow.id,
        'role': workflow.role,
        'recruiter': workflow.recruiter,
        'candidate': workflow.candidate,
        'status': workflow.status,
    }


def update_assessment_status(workflow_id: str, status: str) -> None:
    workflow = _WORKFLOWS[workflow_id]
    workflow.status = status


def get_assessment_status(workflow_id: str) -> str:
    return _WORKFLOWS[workflow_id].status


def submit_evaluation(workflow_id: str, score: int, decision: str) -> None:
    workflow = _WORKFLOWS[workflow_id]
    workflow.evaluation = {'score': score, 'decision': decision}


def get_evaluation(workflow_id: str) -> Dict[str, object]:
    return _WORKFLOWS[workflow_id].evaluation or {}
