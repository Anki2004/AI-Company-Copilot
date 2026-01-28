from typing import Dict, List, Any, Optional, Set
from datetime import datetime
import asyncio
import json

from ..models.workflow import Workflow
from ..models.task import Task
from ..tools import get_tool_by_name
from ..utils.llm import LLMClient
from ..utils.logger import log_execution
from ..core.planner import Planner

class Executor:
    def __init__(self, db, llm:LLMClient):
        self.db = db
        self.llm = llm
        self.planner = None
        self.max_retries = 3
        self.max_concurrent_tasks =5
        
    def set_planner(self, planner:Planner):
        self.planner = planner


    async def run_workflow(self,workflow_id:str):
        workflow = self.db.query(Workflow).filter(Workflow.id == workflow_id).first()

        if not workflow:
            raise ValueError(f"Workflow {workflow_id} not found")
        
        workflow.status = "executing"
        workflow.updated_at = datetime.now()
        self.db.commit()

        try:
            tasks = self.db.query(Task).filter(
                Task.workflow_id == workflow_id

            ).order_by(Task.order).all()

            if not tasks:
                workflow.status = "completed"
                self.db.commit()
                return 
            await self._execute_task_graph(workflow, tasks)

            self.db.refresh(workflow)

            if workflow.status == "executing":
                all_tasks = self.db.query(Task).filter(Task.workflow_id == workflow_id).all()

                completed = sum(1 for t in all_tasks if t.status == "completed")
                failed = sum(1 for t in all_tasks if t.status == "failed")

                if failed > 0:
                    workflow.status = "failed"
                elif completed == len(all_tasks):
                    workflow.status = "completed"
                workflow.updated_at = datetime.now()
                self.db.commit()
            log_execution("workflow_executed", {
                "workflow_id":workflow_id,
                "status":workflow.status,
                "tasks_completed":workflow.completed_tasks,
                "total_tasks":workflow.total_tasks
            })

        except Exception as e:
            workflow.status = "failed"
            workflow.updated_at = datetime.now()
            self.db.commit()
            log_execution("workflow_execution_failed", {
                "workflow_id":workflow_id,
                "error":str(e)
            })

            raise

    async def _execute_task_graph(self, workflow:Workflow, tasks:List[Task]):
        task_map  = {task.id: task for task in tasks}
        task_by_order = {task.order:task for task in tasks}

        completed_orders:Set[int] = set()
        running_tasks = set()
        while len(completed_orders) < len(tasks):
            ready_tasks = self._get_ready_tasks(tasks, completed_orders, running_tasks)
            if not ready_tasks:
                if running_tasks:
                    await asyncio.sleep(0.5)
                    continue

                else:
                    break
            batch = ready_tasks[:self.max_concurrent_tasks]
            results = await asyncio.gather(
                *[self._execute_task(workflow, task, task_by_order) for task in batch],
                return_exceptions = True
            )
            for task, result in zip(batch, results):
                if isinstance(result, Exception):
                    log_execution("task_execution_error", {
                        "task_id":task.id,
                        "error":str(result)
                    })
                self.db.refresh(task)

                if task.status =="completed":
                    completed_orders.add(task.order)
                elif task.status == "failed":
                    await self._handle_task_failure(workflow, task)
                running_tasks.discard(task.id)



            workflow.completed_tasks = len(completed_orders)
            workflow.updated_at = datetime.now()
            self.db.commit()

            self.db.refresh(workflow)
            if workflow.approval_needed:
                break


    def _get_ready_tasks(
            self, 
            tasks:List[Task],
            completed_orders:Set[int],
            running_tasks:Set[str]
    )->List[Task]:
        
        ready = []
        for task in tasks:
            if task.status !=  "pending":
                continue
            if task.id in running_tasks:
                continue

            deps_statisfied = all(dep in completed_orders for dep in task.dependencies)
            if deps_statisfied:
                ready.append(task)

        return ready

    async def _execute_task(self, workflow:Workflow, task:Task,task_by_order:Dict[int, Task] )->Dict[str, Any]:
        task.status = "running"
        task.started_at = datetime.now()
        workflow.current_task_id = task.id
        self.db.commit()

        log_execution("task_started", {
            "task_id":task.id,
            "workflow_id":workflow.id,
            "tool":task.tool_name
        })
        try:
            tool = get_tool_by_name(task.tool_name)
            if not tool:
                raise ValueError(f"Tool '{task.tool_name} not found")
            tool_input = await self._prepare_tool_input(
                task.input_data,
                task.dependencies,
                task_by_order

            )

            result = await tool.execute(**tool_input)

            if task.tool_name == "approval":
                workflow.approval_needed = True
                workflow.approval_context = result
                workflow.updated_at = datetime.now()
                task.status = "completed"
                task.output_data = result
                task.completed_at = datetime.now()
                self.db.commit()

                log_execution("approval_requested", {
                    "workflow_id":workflow.id,
                    "context":result
                })

                return result

            task.status = "completed"
            task.output_data = result
            task.completed_at = datetime.now()
            self.db.commit()

            log_execution("task_completed", {
                "task_id":task.id,
                "tool":task.tool_name,
                "output_preview":str(result)[:200]
            })
            return result
        
        except Exception as e:
            task.status = "failed"
            task.error = str(e)
            task.completed_at = datetime.now()
            self.db.commit()

            log_execution("task_failed", {
                "task_id":task.id,
                "tool":task.tool_name,
                "error":str(e)
            })

            raise

    async def _prepare_tool_input(self, raw_input:Dict[str, Any], dependencies:List[int], task_by_order:Dict[int, Task])->Dict[str, Any]:
        dep_outputs=[]
        for dep_order in dependencies:
            dep_task = task_by_order.get(dep_order)
            if dep_task and dep_task.output_data:
                dep_outputs[f"task_{dep_order}_output"] = dep_task.output_data
                dep_outputs[f"{dep_task.tool_name}_results"] = dep_task.output_data


        prepared_input = self._substitute_parameters(raw_input, dep_outputs)
        return prepared_input


    def _substitue_parameters(self, input_data:Any, context_items:Dict[str, Any])->Any:
        if isinstance(input_data, str):
            result = input_data
            for key, value in context_items():
                template = f"{{{{{key}}}}}"
                if template in result:
                    if result == template:
                        return value

                    result = result.replace(template, str(value))
            return result

        elif isinstance(input_data, dict):
            return {
                key:self._substitue_parameters(value, context_items)
                for key, value in input_data.items()
            }
        elif isinstance(input_data, list):
            return [
                self._substitue_parameters(item, context_items)
                for item in input_data

            ]

        else:
            return input_data

    async def _handle_task_failure(self, workflow:Workflow, task:Task):
        retry_count = task.input_data.get("_retry_count", 0)
        if retry_count < self.max_retries:
            task.status = "pending"
            task.error= None
            task.input_data["_retry_count"] = retry_count+1
            self.db.commit()

            log_execution("task_retrying", {
                "task_id":task.id,
                "retry_count":retry_count+1
            })

            await asyncio.sleep(2 ** retry_count)

        else:
            if self.planner:
                log_execution("task_new_retries", {
                    "task_id":task.id,
                    "requesting_replan":True
                })
                await self.planner.replan_from_failure(
                    workflow, 
                    task,
                    task.error or "unknown error"
                )
            else:
                workflow.status = "failed"
                self.db.commit()










        


