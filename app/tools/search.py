from typing import List, Dict,Any, Optional
from .base import BaseTool
from ..core.rag import RAG
from ..database import SessionLocal


class SearchTool(BaseTool):
    def __init__(self):
        super().__init__()
        self.name = 'search'
        self.description = "Search company documents, tickets, code and knowledge base"
        self.category = "search"

    async def execute(self, query:str, filters:Optional[Dict[str, Any]] = None, limit:int=10, hybrid:bool = True)->Dict[str, Any]:
        self.validate_input(query=query)
        db=SessionLocal()

        try:
            rag = RAG(db)
            if hybrid:
                results = rag.search_hybrid(query, filters=filters, limit=limit)
            else:
                results = await rag.search(query, filters=filters, limit=limit)

            return {
                "results":results,
                "query":query,
                "total":len(results),
                "filters":filters
            }
        finally:
            db.close()

    def get_paramters_schema(self)->Dict[str, Any]:
        return {
            "query":{"type":"string", "required":True},
            "filters":{"type":"object", "required":False},
            "limit":{"type":"integer", "required":False},
            "hybrid":{"type":"boolean", "required":False}
        }
    



