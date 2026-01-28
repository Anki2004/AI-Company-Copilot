from fastapi import APIRouter, HTTPExtension, Depends, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, UTC
import uuid

from ..database import get_db
from ..models.goals import Goal
from ..models.workflow import Workflow
from ..core.agent import Agent
from ..core.planner import Planner


router = APIRouter(prefix="/api/goals", tags=["goals"])
class GoalCreate(BaseModel):
    description:str
    context:Optional[dict] = None
    priority:Optional[str] = "medium"

class GoalResponse(BaseModel):
    id:str
    description:str
    status:str
    workflow_id:Optional[str] = None
    created_at:datetime
    updated_at:datetime
    result:Optional[dict] = None

async def run_background_task(goal_id:str, db):
    agent = Agent(db)
    await agent.process_goal(goal_id)



@router.post("/", response_model = GoalResponse)
async def create_goal(goal:GoalCreate, background_tasks:BackgroundTasks, db=Depends(get_db)):
    goal_id = str(uuid.uuid4())
    new_goal = Goal(
        id = goal_id,
        description = goal.description,
        context = goal.context,
        priority = goal.priority,
        status = "pending",
        created_at = datetime.now(UTC),
        update_at = datetime.now(UTC)
    )
    db.add(new_goal)
    db.commit()
    db.refresh()

    background_tasks.add_task(run_background_task, goal_id, db)

    return GoalResponse(
        id=new_goal.id,
        description = new_goal.description,
        status = new_goal.status,
        workflow_id = None,
        created_at = new_goal.created_at,
        updated_at = new_goal.updated_at,
        result = None
    )

@router.get("/{goal_id}", response_model = GoalResponse )
async def get_goal(goal_id:str, db = Depends(get_db)):
    goal = db.query(Goal).filter(Goal.id== goal_id).first()
    if not goal:
        raise HTTPExtension(status_code = 404, detail = "Goal not Found")
    
    workflow = db.query(Workflow).filter(Workflow.goal_id == goal_id)
    return GoalResponse(
        id = goal.id,
        description = goal.description,
        status = goal.status,
        workflow_id = workflow.id if workflow else None,
        created_at = goal.created_at,
        updated_at = goal.updated_at,
        result = goal.result
    )

@router.get("/", response_model = List[GoalResponse])

async def list_goals(status:Optional[str]=None, limit:int = 50, db=Depends(get_db)):
    query =db.query(Goal)
    if status:
        query = query.filter(Goal.status == status)

    goals = query.order_by(Goal.created_at.desc()).limit(limit).all()
    return [
        GoalResponse(
            id=goal.id,
            description = goal.description,
            status = goal.status,
            workflow= goal.workflow,
            created_at = goal.created_at,
            updated_at = goal.updated_at,
            result = goal.result
        )
        for goal in goals
    ]