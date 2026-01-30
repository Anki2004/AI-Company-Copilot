from typing import Dict, Any, Optional, List
from .base import BaseTool
from ..database import SessionLocal
from sqlalchemy import text

class ExtractionTool(BaseTool):
    def __init__(self):
        super().__init__()
        self.name = "extract"
        self.description = "Extract data from databases using SQL or API calls"
        self.category = "data"

    async def execute(self, source:str, query:Optional[str] = None, api_endpoint:Optional[str] = None, parameters:Optional[Dict[str, Any]] = None)->Dict[str, Any]:
        self.validate_input(source = source)

        if source =="database" and query:
            return await self._execute_sql(query, parameters or {})
        
        elif source =="jira":
            return await self._fetch_jira_tickets(parameters or {})
        elif source == "github":
            return await self._fetch_github_data(parameters or {})

        else:
            raise ValueError(f"Unsupported sourc:{source}")

    async def _execute_sql(self, query:str, parameters:Dict[str, Any])->Dict[str, Any]:
        if not query.strip().upper().startswith("SELECT"):
            raise ValueError("Only SELECT queries not found")
        db = SessionLocal()
        try:
            result = db.execute(text(query), parameters)
            rows = result.fetchall()

            columns = result.keys()
            data = [dict(zip(columns, row)) for row in rows]

            return {
                "data":data,
                "count":len(data),
                "query":query
            }
        
        finally:
            db.close()

    async def _fetch_jira_tickets(self, parameters:Dict[str, Any])->Dict[str, Any]:
        import os
        import httpx

        jira_url = os.getenv("JIRA_URL")
        jira_token = os.getenv("JIRA_TOKEN")

        if not jira_url or not jira_token:
            raise ValueError("Jira url and token not provided")
        
        jql_parts = []
        if "project" in parameters:
            jql_parts.append(f"Project = {parameters['project']}")
        if "status" in parameters:
            jql_parts.append(f"Status = '{parameters['status']}'")
        if "date_from" in parameters:
            jql_parts.append(f"Created >= '{parameters['date_from']}'")

        jql = "AND".join(jql_parts) if jql_parts else "order by created DESC"


        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{jira_url}/rest/api/3/search",
                headers={"Authorization": f"Bearer {jira_token}"},
                params={"jql": jql, "maxResults": parameters.get("limit", 50)}
            )

            response.raise_for_status()
            data = response.json()
            tickets = data.get("issues",[])

            return {
                "tickets":tickets,
                "count":len(tickets),
                "total":data.get("total", 0)
            }
    async def _fetch_github_data(self, parameters:Dict[str, Any])->Dict[str, Any]:
        import os
        import httpx

        github_token = os.getenv("GITHUB_TOKEN")

        if not github_token:
            raise ValueError("Github credentials required!")
        
        repo = parameters.get("repo")
        data_type = parameters.get("type", "issues")

        if not repo:
            raise ValueError("Repository name required")
        
        async with httpx.AsyncClient() as client:
            url = f"https://api.github.com/repos/{repo}/{data_type}"
            response = await client.get(
                url,
                headers={"Authorization": f"token {github_token}"},
                params={"state": parameters.get("state", "all"), "per_page": parameters.get("limit", 30)}
            )
            response.raise_for_status()
            data =response.json()

            return {
                "data":data,
                "count":len(data),
                "repo":repo,
                "type":data_type
            }
    def get_paramters_schema(self)->Dict[str, Any]:
        return {
            "source":{"type":"string", "required":True},
            "query":{"type":"string", "required":False},
            "api_endpoint":{"type":"string", "required":False},
            "parameters":{"type":"object", "required":False}
        }
    
        




