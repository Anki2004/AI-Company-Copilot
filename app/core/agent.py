from typing import Optional, Dict, Any, List
from datetime import datetime
import json

from ..models.goals import Goal
from ..models.workflow import Workflow
from ..models.task import Task
from ..core.planner import Planner
from ..core.executor import Executor
from ..core.rag import RAG
from ..utils.llm import LLMClient
from ..utils.logger import log_execution


class Agent:
    def __init__(self, db):
        self.db = db
        self.llm = LLMClient()
        self.planner = Planner(db, self.llm)
        self.executor = Executor(db, self.llm)
        self.rag = RAG(db)

    async def process_goal(self, goal_id:str):
        goal = self.db.query(Goal).filter(Goal.id == goal_id).first()

        if not goal:
            raise ValueError(f"Goal {goal_id} not found")
        try:
            goal.status = "planning"
            self.db.commit()

            parsed_goal = await self._parse_goal(goal)
            workflow = await self.planner.create_workflow(goal, parsed_goal)

            goal.status = "executing"
            self.db.commit()


            await self.executor.run_workflow(workflow.id)

            self.db.refresh(workflow)
            if workflow.approval_needed:
                goal.status = "awaiting_approval"
            elif workflow.status == "completed":
                goal.status = "completed"
                goal.result = workflow.approval_context
            elif workflow.status == "failed":
                goal.status = "failed"

            goal.updated_at = datetime.now()
            self.db.commit()

            log_execution("goal_processed",{
                "goal_id":goal_id,
                "workflow_id":workflow.id,
                "status":goal.status
            })

        except Exception as e:
            goal.status = "failed"
            goal.result = {"error":str(e)}
            self.db.commit()
            log_execution("goal_failed", {"goal_id":goal_id, "error":str(e)})
            raise

    async def _parse_goal(self, goal:Goal) ->Dict[str, Any]:
        context = await self.rag.search(goal.description, limit=5)
        context_text = "\n".join([
            f"- {doc['metadata'].get('title','Untitled')}:{doc['content'][:200]}"
            for doc in context
        ])
        prompt = f"""Parse this user goal into a structured format.

Goal: {goal.description}

Additional Context from User: {json.dumps(goal.context, indent=2)}

Relevant Knowledge Base Context:
{context_text}

Extract and return JSON with:
1. "intent": What does the user want to accomplish? (analyze, create, update, retrieve, etc.)
2. "required_data": What data sources are needed? (docs, tickets, code, databases)
3. "output_format": What should the final output be? (report, dashboard, document, data file)
4. "constraints": Any time bounds, filters, or specific requirements
5. "steps_hint": High-level steps you think are needed

Return ONLY valid JSON, no markdown or explanation."""
        
        response = await self.llm.complete(prompt)

        try:
            parsed = json.loads(response)
            log_execution("goal_parsed", {"goal_id":goal.id, "parsed":parsed})
            return parsed
        except Exception as e:
            return {
                "intent":"general",
                "required_data":["docs"],
                "output_format":"text",
                "constraints":{},
                "steps_hint":["search", "analyze", "write"]
            }
        
    async def handle_approval(self, workflow_id:str, approved:bool, feedback:Optional[str]):
        workflow = self.db.query(Workflow).filter(Workflow.id == workflow_id).first()

        if not workflow:
            raise ValueError(f"Workflow {workflow_id} not found")

        goal = self.db.query(Goal).filter(Goal.id == workflow.goal_id).first()

        if approved:
            workflow.status = 'completed'
            workflow.approval_needed = False
            goal.status = "completed"
            goal.result = workflow.approval_context

            self.db.commit()
            log_execution("workflow_approved", {"workflow_id":workflow_id})


        else:
            workflow.approval_needed = False
            workflow.status = "executing"
            self.db.commit()
            log_execution("workflow_rejected", {
                "workflow_id":workflow_id,
                "feedback":feedback
            })


            await self._iterate_workflow(workflow, feedback)
    async def _iterate_workflow(self, workflow:Workflow, feedback:Optional[str]):
        goal = self.db.query(Goal).filter(Goal.id == workflow.goal_id).first()
        tasks = self.db.query(Task).filter(Task.workflow_id == workflow.id).all()

        task_summary = "\n".join([
            f"- {task.tool_name}:{task.status} (output:{json.dumps(task.output_data)[:100]})"
            for task in tasks
        ])

        prompt = f"""A workflow needs iteration based on user feedback.

Original Goal: {goal.description}

Current Workflow Tasks:
{task_summary}

User Feedback: {feedback or "Not satisfied with results"}

Previous Output:
{json.dumps(workflow.approval_context, indent=2)[:500]}

What should be changed? Return JSON with:
1. "tasks_to_retry": List of task tool names to re-run
2. "new_tasks": List of new tasks to add (tool_name, description, input_data)
3. "adjustments": Any parameter changes for existing tasks

Return ONLY valid JSON."""
        response = await self.llm.complete(prompt)

        try:
            iteration_plan = json.loads(response)

            for task_name in iteration_plan.get("task_to_retry", []):
                task = next((t  for t in tasks if t.tool_name == task_name), None)

                if task:
                    task.status = "pending"
                    task.output_data = None
                    task.error = None

            for new_task_data in iteration_plan.get("new_tasks", []):
                new_task =Task(
                    workflow_id = workflow.id,
                    tool_name = new_task_data["tool_name"],
                    description = new_task_data.get("description"),
                    order = len(tasks) + 1,
                    input_data = new_task_data["input_data"],
                    status="pending"
                )
                self.db.add(new_task)
                workflow.total_tasks += 1

            self.db.commit()

            await self.executor.run_workflow(workflow.id)
        except Exception as e:
            log_execution("iteration_failed", {
                "workflow_id":workflow.id,
                "error":str(e)
            })
            workflow.status = "failed"
            self.db.commit()
            raise

        

