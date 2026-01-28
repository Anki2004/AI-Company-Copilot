from typing import List, Dict, Any, Optional
import numpy as np
from datetime import datetime
from sqlalchemy import text

from ..models.document import Document
from ..utils.llm import LLMClient
from ..utils.logger import log_execution

class RAG:

    def __init__(self, db):
        self.db = db
        self.llm = LLMClient()
        self.embedding_model = "text-embedding-3-small"
        self.default_limit = 10
        self.rerank_enabled = True

    async def search(self, query:str, filters:Optional[Dict[str, Any]] = None, limit:int=10, min_score:float=0.5)->List[Dict[str, Any]]:
        query_embedding = await self._get_embedding(query)
        results = await self._vector_search(
            query_embedding,
            filters = filters,
            limit = limit * 2
        )
        if self.rerank_enabled and len(results) > limit:
            results = await self._rerank_results(query, results, limit)

        results = [r for r in results if r["score"] >= min]
        log_execution("rag_search", {
            "query":query[:100],
            "num_results":len(results),
            "filters":filters
        })
        return results[:limit]

    async def search_hybrid(self, query:str, filters:Optional[Dict[str, Any]]=None, limit:int=10, vector_weight:float=0.7,)->List[Dict[str, Any]]:
        query_embedding = await self._get_embedding(query)
        vector_results = await self._vector_search(
            query_embedding,
            filters = filters,
            limit = limit
        )

        keyword_search = await self._keyword_search(
            query, 
            filters = filters,
            limit = limit
        )
        combined = self._merge_results(
            vector_results,
            keyword_search,
            vector_weight = vector_weight
        )

        return combined[:limit]
    
    async def get_context_for_task(self, task_description:str, previous_output:List[Dict[str, Any]] = None, limit:int=5)->str:
        results = await self.search(task_description, limit=limit)

        context_results = []
        for i, result in enumerate(results):
            metadata = result["metadata"]
            title = metadata.get("title", "Untitled")
            source = result["source"]

            context_results.append(
                f"[{i+1}]{title}(from {source})\n{result["content"]}\n"
            )
        if previous_output:
            context_results.append("\n...Previous Task Ouptuts...")
            for i, output in enumerate(previous_output):
                context_results.append(f"Task {i}:{str(output)[:200]}")

        context = "\n".join(context_results)

        return context

    async def _get_embedding(self, text:str)->List[float]:
        try:
            import openai
            import os
            client = openai.OpenAI(api_key = os.getenv("OPENAI_API_KEY"))
            response = client.embeddings.create(
                model = self.embedding_model,
                input = text
            )

            return response.data[0].embedding
        

        except Exception as e:
            log_execution("embedding_failed", {"error":str(e)})
            return [0.0]*1536
        
    async def _vector_search(self, query_embedding:List[float], filters:Optional[Dict[str, Any]]=None, limit:int=10)->List[Dict[str, Any]]:
        filter_conditions = []
        filter_params = {"query_embedding":query_embedding, "limit":limit}

        if filters:
            if "source" in filters:
                filter_conditions.append("source = :source")
                filter_params["source"] = filters["source"]

            if "doc_type" in filters:
                filter_conditions.append("doc_type = :doc_type")
                filter_params["doc_type"] = filters["doc_type"]

            if "date_from" in filters:
                filter_conditions.append("source_updated_at >= :date_from")
                filter_params["date_from"] = filters["date_from"]

            if "date_to" in filters:
                filter_conditions.append("source_updated_at <= :date_to")
                filter_params["date_to"] = filters["date_to"]

        where_clause = f"WHERE {'AND'.join(filter_conditions)}" if filter_conditions else ""

        query = text(f"""
SELECT 
                id,
                content,
                source,
                source_id,
                source_url,
                title,
                author,
                doc_type,
                metadata,
                1 - (embedding <=> :query_embedding) as score
            FROM documents
            {where_clause}
            ORDER BY embedding <=> :query_embedding
            LIMIT :limit
""")
        
        result = self.db.execute(query, filter_params)
        rows = result.fetchall()

        results = []
        for row in rows:
            results.append({
                "id":row.id,
                "content":row.content,
                "source":row.source,
                "metadata":{
                    "title":row.title,
                    "author":row.author,
                    "doc_type":row.doc_type,
                    "source_url":row.source_url,
                    **row.metadata
                },
                "source":float(row.score)
            })

        return results
    async def _keyword_search(self, query:str, filters:Optional[Dict[str, Any]] = None, limit:int=10):
        filter_conditions = []
        filter_params = {"query":query, "limit":limit}

        if filters:
            if "source" in filters:
                filter_conditions.append("source = :source")
                filter_params["source"] = filters["source"]

            if "doc_type" in filters:
                filter_conditions.append("doc_type = :doc_type")
                filter_params["doc_type"] = filters["doc_type"]

        where_clause = f"AND {'AND'.join(filter_conditions)}" if filter_conditions else ""

        query_sql = text(f"""
SELECT 
                id,
                content,
                source,
                source_id,
                source_url,
                title,
                author,
                doc_type,
                metadata,
                ts_rank(to_tsvector('english', content), plainto_tsquery('english', :query)) as score
            FROM documents
            WHERE to_tsvector('english', content) @@ plainto_tsquery('english', :query)
            {where_clause}
            ORDER BY score DESC
            LIMIT :limit
""")
        
        result = self.db.execute(query_sql, filter_params)
        rows = result.fetchall()


        results =[]
        for row in rows:
            results.append({
                "id":row.id,
                "content":row.content,
                "source":row.source,
                "metadata":{
                    "title":row.title,
                    "author":row.author,
                    "doc_type":row.doc_type,
                    "source_url":row.source_url,
                    **row.metadata
                },
                "source":float(row.score)
            })


        return results
    
    def _merge_results(self, vector_results:List[Dict[str, Any]], keyword_results:List[Dict[str, Any]], vector_weights:float=0.7)->List[Dict[str, Any]]:
        def normalize_source(results):
            if not results:
                return []
            max_score = max(r["score"]for r in results)
            min_score = min(r["score"] for r in results)
            range_score = max_score-min_score if max_score > min_score else 1.0

            for r in results:
                r["normalized_score"] = (r["score"]- min_score / max_score)
            return results

        vector_results =normalize_source(vector_results)
        keyword_results = normalize_source(keyword_results)

        combined = {}
        keyword_weight = 1.0 - vector_weights

        for result in vector_results:
            doc_id= result["id"]
            combined[doc_id] = result.copy()
            combined[doc_id]["final_score"] = result["normalized_score"] * vector_weights

        for result in keyword_results:
            doc_id = result["id"]
            if doc_id in combined:
                combined[doc_id]["final_score"] += result["normalized_score"] *  keyword_results
            else:
                combined[doc_id] = result.copy()
                combined[doc_id]["final_score"] = result["normalized_score"] * keyword_results

        merged = list(combined.values())
        merged.sort(key=lambda x:x["final_score"], reverse = True)

        return merged
    
    async def _rerant_results(self, query:str, results:List[Dict[str, Any]], limit:int)->List[Dict[str, Any]]:
        if len(results) <= limit:
            return results
        
        doc_texts = "\n\n".join([
            f"[{i}] {r['metadata'].get('title', 'Untitled')}\n{r['content'][:300]}"
            for i, r in enumerate(results)
        ])


        prompt = f"""Rank these documents by relevance to the query.

Query: {query}

Documents:
{doc_texts}

Return ONLY a JSON array of document indices in order of relevance (most relevant first).
Example: [3, 0, 5, 1, 2]

Return top {limit} most relevant indices."""
        
        try:
            response = await self.llm.comlete(prompt, max_tokens=500)
            response = response.strip()

            if response.startswith("```json"):
                response = response[7:-3]
            import json
            ranked_indicies = json.loads(response)

            reranked = []
            for idx in ranked_indicies[:limit]:
                if 0 <= idx < len(results):
                    reranked.append(results[idx])

            if len(reranked) < limit:
                for i, r in enumerate(results):
                    if i not in ranked_indicies and len(reranked) < limit:
                        reranked.append(r)
            log_execution("reranking_completed", {
                "original_count":len(results),
                "reranked_count":len(reranked)
            })

            return reranked
        except Exception as e:
            log_execution("reranking_failed", {"error":str(e)})
            return results[:limit]
        
    async def get_similar_documents(self, doc_id:str, limit:int=5)->List[Dict[str, Any]]:
        doc = self.db.query(Document).filter(Document.id == doc_id).first()
        if not doc or not doc.embedding:
            return []

        results = await self._vector_search(
            doc.embedding,
            limit = limit+1
        )
        results = [r for r in results if r["id"] != doc_id]

        return results[:limit]
    

    




