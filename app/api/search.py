from fastapi import APIRouter, HTTPExtension, Depends
from pydantic import BaseModel
from typing import List, Optional

from ..database import get_db
from ..core.rag import RAG


router = APIRouter(prefix="/api/search", tags=["search"])
class SearchRequest(BaseModel):
    query:str
    filters:Optional[dict] = None
    limit:int=10


class SearchResult(BaseModel):
    id:str
    content:str
    source:str
    metadata:dict
    score:float


class SearchResponse(BaseModel):
    results:List[SearchResult]
    total:int

@router.post("/", response_model = SearchResponse)
async def semantic_search(request:SearchRequest, db=Depends(get_db)):
    rag = RAG(db)
    results= await rag.search(
        query=request.query,
        filters=request.filters,
        limit = request.limit
    )
    search_results=[
        SearchResult(
            id=result["id"],
            content=result["content"],
            source = result["source"],
            metadata = result["metadata"],
            score = result["score"]
        )
        for result in results
    ]
    return SearchResponse(
        results = search_results,
        total = len(search_results)
    )

    