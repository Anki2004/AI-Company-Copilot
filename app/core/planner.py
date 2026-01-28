from typing import Dict, Any, List
from datetime import datetime
import json
import uuid

from ..models.goals import Goal
from ..models.workflow import Workflow
from ..models.task import Task
from ..tools import get_all_tools
from ..utils.llm import LLMClient
from ..utils.logger import log_execution

class Planner:
    def __init__(self, db, llm:LLMClient):
        self.db = db
        self.llm = llm
        self.available_tools = get_all_tools()

    async def create_workflow(self, goal:Goal, parsed_goal:Dict[str, Any])->Workflow:
        workflow = Workflow(
            id=str(uuid.uuid4()),
            goal_id = goal.id,
            status = "pending",
            created_at = datetime.now(),
            updated_at = datetime.now()
        )
        self.db.add(workflow)
        self.db.commit()
        self.db.refresh(workflow)


        try:
            task_plan = await self._generate_task_plan(goal, parsed_goal)
            tasks = await self._create_tasks(workflow, task_plan)

            workflow.total_tasks = len(tasks)
            workflow.status = "executing"
            workflow.updated_at = datetime.now()
            self.db.commit()

            log_execution("workflow_planned",{
                "workflow_id":workflow.id,
                "goal_id":goal.id,
                "total_tasks":len(tasks)
            })

            return workflow
        
        except Exception as e:
            workflow.status = "failed"
            self.db.commit()
            log_execution("workflow_planning_failed", {
                "workflow_id":workflow.id,
                "error":str(e)

            })
            raise
    async def _generate_task_plan(self, goal:Goal, parsed_goal:Dict[str,Any])->List[Dict[str, Any]]:
        tool_descriptions = self._build_tool_descriptions()
        prompt = f"""You are a workflow planner. Create a detailed task plan to accomplish this goal.

        GOAL: {goal.description}

        PARSED GOAL DETAILS:
        {json.dumps(parsed_goal, indent=2)}

        AVAILABLE TOOLS:
        {tool_descriptions}

        Create a step-by-step plan. For each task, specify:
        1. tool_name: Which tool to use
        2. description: What this task does
        3. input: Parameters for the tool (be specific)
        4. dependencies: List of task indices that must complete first (use 0-based indexing)

        IMPORTANT RULES:
        - Start with search/extract tasks to gather information
        - Then process/analyze the data
        - Finally write/update/create outputs
        - If creating documents, always include an approval task at the end
        - Keep tasks atomic (one tool call per task)
        - Use dependencies to control execution order

        Return ONLY a JSON array of tasks, no markdown or explanation.

        Example format:
        [
        {{
            "tool_name": "search",
            "description": "Search for recent support tickets",
            "input": {{"query": "support issues last week", "filters": {{"type": "bug"}}}},
            "dependencies": []
        }},
        {{
            "tool_name": "write",
            "description": "Create summary report",
            "input": {{"title": "Support Issues Summary", "content": "{{results_from_search}}"}},
            "dependencies": [0]
        }},
        {{
            "tool_name": "approval",
            "description": "Request user approval for report",
            "input": {{"document": "{{results_from_write}}"}},
            "dependencies": [1]
        }}
        ]"""
        
        response = await self.llm.complete(prompt, max_tokens = 4096)
        response = response.strip()

        if response.startswith("```json"):
            response = response[7:]
        if response.startswith("```"):
            response = response[3:]
        if response.endswith("```"):
            response = response[:-3]
        response = response.strip()

        try:
            task_plan = json.loads(response)
            task_plan = self._validate_and_fix_plan(task_plan)

            log_execution("task_plan_generated",{
                "goal_id":goal.id,
                "num_tasks":len(task_plan)
            })

            return task_plan
        except json.JSONDecodeError as e:
            log_execution("task_plan_json_error", {
                "goal_id":goal.id,
                "error":str(e),
                "response":response[:500]
            })
            return self._create_fallback_plan(parsed_goal)


    def _build_tool_descriptions(self)->str:
        descriptions = []
        for tool in self.available_tools:
            params = tool.get_parameters_schema()
            params_desc = ", ".join([f"{k}:{v.get('type', 'any')}" for k, v in params.items()])

            descriptions.append(
                f"- {tool.name}({tool.category}):{tool.description}\n"
                f"- Parameters:{params_desc}"
            )

        return "\n".join(descriptions)
    
    def _validate_and_fix_plan(self, task_plan:List[Dict[str, Any]])->List[Dict[str ,Any]]:
        valid_tool_names = {tool.name for tool in self.available_tools}
        validated_plans=[]

        for i, task in enumerate(task_plan):
            if task["tool_name"]not in valid_tool_names:
                log_execution("invalid tool name",{
                    "tool_name":task["tool_name"],
                    "task_index":i
                })
                continue
            deps = task.get("dependencies", [])
            valid_deps = [d for d in deps if 0<=d <i]
            task["dependencies"] = valid_deps

            if "input" not in task:
                task["input"] = {}
            if "description" not in task:
                task["description"] =f"Execute {task["tool_name"]}"

            validated_plans.append(task)


        has_write = any(t["tool_name"] in ["write", "update", "code"] for t in validated_plans)
        has_approval = any(t["tool_name"]=="approval" for t in validated_plans)

        if has_write and not has_approval:
            validated_plans.append({
                "tool_name":"approval",
                "description":"Request user approval for outputs",
                "input":{"context":"workflow_output"},
                "dependencies":list(range(len(validated_plans)))
            })


        return validated_plans
    
    def _create_fallback_plans(self, parsed_goal:Dict[str, Any])->List[Dict[str, Any]]:
        plan = []
        plan.append({
            "tool_name":"search",
            "description":"search for relevant information",
            "input":{
                "query":parsed_goal.get("intent", "general information"),
                "limit":10
            },
            "dependencies":[]
        })

        if parsed_goal.get("output_format") in ["report", "document", "text"]:
            plan.append({
                "tool_name":"write",
                "description":"Create output document",
                "input":{
                    "title":"Generated Report",
                    "content":"{{search_result}}"

                },
                "dependencies":[0]
            })

            plan.append({
                "tool_name":"approval",
                "description":"Request Approval",
                "input":{"context", "document"},
                "dependencies":[1]
            })
        log_execution("fallback_plan_created",{
            "parsed_goal":parsed_goal,
            "num_tasks":len(plan)
        })
        return plan
    async def _create_tasks(self, workflow:Workflow, task_plan:List[Dict[str,Any]])->List[Dict[str, Any]]:
        tasks = []
        for i, task_spec in enumerate(task_plan):
            task = Task(
                id=str(uuid.uuid4()),
                workflow_id = workflow.id,
                tool_name = task_spec["tool_name"],
                description = task_spec.get("description", ""),
                order = i,
                status = "pending",
                input_data = task_spec["input"],
                dependencies = task_spec.get("dependencies", []),
                created_at = datetime.now()
            )
            self.db.commit()
            tasks.append(task)

        self.db.commit()
        return tasks


    async def replan_from_failure(self, workflow:Workflow, failed_task:Task, error:str)->List[Task]:
        all_tasks = self.db.query(Task).filter(Task.workflow_id == workflow.id).all()
        task_summary = "\n".join([
            f"{i}. {t.tool_name} - {t.status }(deps:{t.dependencies})"
            for i, t in enumerate(all_tasks)
        ])

        prompt = f"""A task in the workflow failed. Suggest how to recover.

FAILED TASK:
- Tool: {failed_task.tool_name}
- Description: {failed_task.description}
- Input: {json.dumps(failed_task.input_data, indent=2)}
- Error: {error}

FULL WORKFLOW:
{task_summary}

Options:
1. Retry with modified input
2. Skip this task and continue
3. Add alternative tasks to work around the failure
4. Abort workflow (if critical failure)

Return JSON with:
{{
  "action": "retry" | "skip" | "add_tasks" | "abort",
  "retry_input": {{...}} if retry,
  "new_tasks": [...] if add_tasks,
  "reason": "explanation"
}}"""
        response = await self.llm.complete(prompt)

        try:
            response = response.strip()
            if response.startswith("```json"):
                response = response[7:-3]

            recovery_plan = json.loads(response)
            if recovery_plan["action"] == "retry":
                failed_task.input_data = recovery_plan["retry_input"]
                failed_task.status = "pending"
                failed_task.error = None
                self.db.commit()
                return [failed_task]

            elif recovery_plan["action"] =="skip":
                failed_task.status = "skipped"
                self.db.commit()
                return []
            
            elif recovery_plan["action"] == "add_task":
                new_tasks = []
                for task_spec in recovery_plan["new_tasks"]:
                    task = Task(
                        workflow_id = workflow.id,
                        tool_name = task_spec["tool_name"],
                        description = task_spec.get("description", ""),
                        order = len(all_tasks) + len(new_tasks),
                        input_data = task_spec["input"],
                        dependencies = task_spec.get("dependencies", []),
                        status ="pending"
                    )
                    self.db.commit()
                    new_tasks.append(task)

                workflow.total_tasks += len(new_tasks)
                self.db.commit()
                return new_tasks
            

            else:
                workflow.status = "failed"
                self.db.commit()
                return []
            
        except Exception as e:
            log_execution("replain_failed", {
                "workflow_id":workflow.id,
                "error":str(e)
            })
            failed_task.status = "skipped"
            self.db.commit()
            return []
        





        


