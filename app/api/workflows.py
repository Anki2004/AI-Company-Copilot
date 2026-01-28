from fastapi import APIRouter, HTTPExtension, Depends, BackgroundTasks
from pydantic import BaseModel
from typing  import List, Optional
from datetime import datetime


from ..database import get_db
from ..models.workflow import Workflow
from ..models.task import Task
from ..models.goals import Goal
from ..core.agent import Agent


router = APIRouter(prefix="/api/workflows", tags = ["workflows"])

class TaskStep(BaseModel):
    id:str
    tool:str
    status:str
    input:dict
    output:Optional[dict]=None
    started_at:Optional[datetime] = None
    completed_at:Optional[datetime] = None

class WorkflowResponse(BaseModel):
    id:str
    goal_id:str
    status:str
    task_graph:List[TaskStep]
    current_step:Optional[str] = None
    approval_needed:bool = False
    approval_context:Optional[dict] = None
    created_at:datetime
    updated_at:datetime

class ApprovalRequest(BaseModel):
    approval:bool
    feedback:Optional[str] = None

@router.get("/{workflow_id}", response_model = WorkflowResponse)
async def get_workflow(workflow_id:str, db=Depends(get_db)):
    workflow = db.query(Workflow).filter(Workflow.id == workflow_id).first()
    if not workflow:
        raise HTTPExtension(status_code = 404, detail = "Workflow not found")
    
    tasks = db.query(Task).filter(Task.workflow_id == workflow_id).order_by(Task.order).all()
    task_steps = [
        TaskStep(
        id=task.id,
        tool = task.tool_name,
        status = task.status,
        input = task.input_data,
        output = task.output_data,
        started_at = task.started_at,
        completed_at = task.completed_at)
        for task in tasks
    ]

    return WorkflowResponse(
        id = workflow.id,
        goal_id = workflow.goal_id,
        status = workflow.status,
        task_graph = task_steps,
        current_step = workflow.current_task_id,
        approval_needed = workflow.approval_needed,
        approval_context = workflow.approval_context,
        created_at = workflow.created_at,
        updated_at = workflow.updated_at
    )


async def continue_workflow_background(workflow_id:str, approved:bool, feedback:Optional[str], db):
    agent = Agent(db)
    await agent.handle_approval(workflow_id , approved, feedback)

@router.post("/{workflow_id}/approve")
async def approve_workflow(workflow_id:str, approval:ApprovalRequest, background_tasks:BackgroundTasks, db=Depends(get_db)):
    workflow = db.query(Workflow).filter(Workflow.id == workflow_id).first()

    if not workflow:
        raise HTTPExtension(status_code=404, detail="workflow not found")
    
    if not workflow.approval_needed:
        raise HTTPExtension(status_code=400, detail="workflow not awaiting approval")

    workflow.approval_needed = False
    workflow.updated_at = datetime.now()
    if approval.approved:
        workflow.status = 'completed'
        goal = db.query(Goal).filter(Goal.id ==workflow.goal_id).first()
        if goal:
            goal.status = "completed"
            goal.result = workflow.approval_context
            goal.updated_at = datetime.now()

        else:
            workflow.status = "executing"
            background_tasks.add_task(
                continue_workflow_background,
                workflow_id,
                approval.approved,
                approval.feedback,
                db
            )

        db.commit()
        return {"status":"success", "workflow_status":workflow.status}
    
@router.post("/{workflow_id}/cancel")
async def cancel_workflow(workflow_id:str, db=Depends(get_db)):
    workflow = db.query(Workflow).filter(Workflow.id ==workflow_id).first()

    if not workflow:
        raise HTTPExtension(status_code = 404, detail="Workflow not found")
    if workflow.status in ["completed", "failed"]:
        raise HTTPExtension(status_code = 400, detail=f"cannot cancel{workflow.status}")

    workflow.status = "cancelled"
    workflow.updated_at = datetime.now()

    goal = db.query(Goal).filter(Goal.id == workflow.goal_id).first()
    if goal:
        goal.status = "cancelled"
        goal.updated_at = datetime.now()

    db.commit()
    return {"status":"success", "message":"workflow completed"}


