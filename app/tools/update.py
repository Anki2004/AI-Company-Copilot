from typing import Dict, Any, Optional
from .base import BaseTool
from ..database import SessionLocal
from sqlalchemy import text

class UpdateTool(BaseTool):
    def __init__(self):
        super().__init__()
        self.name = "update"
        self.description = "Update records in databases or external systems (Jira, etc)"
        self.category = "data"

    async def execute(self, target:str, record_id:str, updates:Dict[str, Any], condition:Optional[Dict[str, Any]])->Dict[str, Any]:

        self.validate_input(target = target, record_id = record_id, updates = updates)
        if target == "jira":
            return await self._update_jira_ticket(record_id, updates)
        elif target == "database":
            return await self._update_database(record_id, updates, condition or {})
        else:
            raise ValueError(f"Unsupported target:{target}")

    async def _update_jira_ticket(self, ticket_id:str, updates:Dict[str, Any])->Dict[str, Any]:
        import httpx
        import os

        jira_url = os.getenv("JIRA_URL")
        jira_token = os.getenv("JIRA_TOKEN")

        async with httpx.AsyncClient() as client:
            response = await client.put(
                f"{jira_url}/rest/api/3/issue/{ticket_id}",
                headers={
                    "Authorization": f"Bearer {jira_token}",
                    "Content-Type": "application/json"
                },
                json={"fields": updates}
            )
            if response.status_code == 204:
                return {
                    "success":True,
                    "ticket_id":ticket_id,
                    "updates":updates
                }
            else:
                raise ValueError(f"Jira update failed:{response.text}")
            

    async def _update_response(self, record_id:str, updates:Dict[str, Any], condition:Dict[str, Any])->Dict[str, Any]:
        db= SessionLocal()
        try:
            set_clause = ", ".join([f"{k} = :{k}" for k in updates.keys()])
            table = condition.get("table", "records")
            query = text(f"UPDATE {table} SET {set_clause} WHERE id = :record_id")
            params = {**updates, "record_id":record_id}
            result = db.execute(query, params)
            db.commit()

            return {
                "success":True,
                "record_id":record_id,
                "row_affected":result.rowcount
            }
        finally:
            db.close()

    def get_paramters_schema(self)->Dict[str, Any]:
        return {
            "target":{"type":"string", "required":True},
            "record_id":{"type":"string", "required":True},
            "updates":{"type":"object", "required":True},
            "condition":{"type":"object", "required":False}


        }






        
