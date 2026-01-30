from typing import Dict, Any, Optional
from .base import BaseTool
from datetime import datetime
import os

class WriteTool(BaseTool):
    def __init__(self):
        super().__init__()
        self.name = "write"
        self.description = "Creata documents, reports or files"
        self.category = "document"

    async def execute(self, title:str, content:str, format:str = "markdown", destination:str = "local", metadata:Optional[Dict[str, Any]] = None) ->Dict[str, Any]:
        self.validate_input(title = title, content = content)

        if destination == "local":
            return await self._write_local(title, content, format, metadata or {})
        elif destination == "gdrive":
            return await self._write_gdrive(title, content, format, metadata or {})
        elif destination =="confluence":
            return await self._write_confluence(title, content, format, metadata or {})
        
        else:
            raise ValueError(f"Unsupported destination:{destination}")
        
    async def _write_local(self, title:str, content:str, format:str, metadata:dict[str, Any])->Dict[str, Any]:
        output_dir = os.getenv("OUTPUT_DIR", "./outputs")
        os.makedirs(output_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).strip()
        filename = f"{timestamp}_{safe_title}.{format}"
        filepath = os.path.join(output_dir, filename)


        with open(filepath , "w", encoding = 'utf-8') as f:
            if format == "markdown":
                f.write(f"# {title}\n\n")
                if metadata:
                    f.write(f"*Metadata: {metadata}*\n\n")

                f.write(content)
            else:
                f.write(content)

        return {
            "success":True,
            "filepath":filepath,
            "title":title,
            "format":format,
            "size_bytes":os.path.getsize(filepath)
        }
    async def _write_gdrive(self, title:str, content:str, format:str, metadata:Dict[str, Any])->Dict[str, Any]:
        local_result = await self._write_local(title, content, format, metadata)
        return{
            "success":True,
            "location":"gdrive",
            "title":title,
            "message":"Google drive integration pending - saved locally",
            "local_path":local_result["filepath"]
        }

    async def _write_confluence(self, title:str, content:str, format:str, metadata:Dict[str, Any])->Dict[str, Any]:
        import httpx
        import os

        confluence_url = os.getenv("CONLFUENCE_URL")
        confluence_token = os.getenv("CONFLUENCE_TOKEN")

        space_key = metadata.get("space_key",os.getenv("CONFLUENCE_SPACE"))
        if not confluence_url or not confluence_token:
            raise ValueError("Confluence credentials required")
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{confluence_url}/rest/api/content",
                headers={
                    "Authorization": f"Bearer {confluence_token}",
                    "Content-Type": "application/json"
                },
                json = {
                    "type":'page',
                    "title":title,
                    "space":{"key":space_key},
                    "body":{
                        "storage":{
                            "value":content,
                            "representation":"storage"
                        }
                    }
                }
            ) 
            if response.status_code == 200:
                data = response.json()
                return {
                    "success":True,
                    "page_id":data.get("id"),
                    "page_url":data.get("_links", {}).get("webui"),
                    "title":title

                }
            else:
                raise ValueError(f"Confluence API error:{response.text}")


    def get_paramters_schema(self)->Dict[str, Any]:
        return {
            "title":{"type":"string", "required":True},
            "content":{"type":"string", "required":True},
            "format":{"type":"string", "required":False},
            "destination":{"type":"string", "required":False},
            "metadat":{"type":"object", "required":False}
        }








