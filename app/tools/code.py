from typing import List, Dict, Any, Optional
from .base import BaseTool
import os
import subprocess

class Code(BaseTool):
    def __init__(self):
        super().__init__()
        self.name = "code"
        self.description = "Read, write or execute code files"
        self.category = "code"

    async def execute(self, operation:str, filepath:Optional[str] = None, content:Optional[str] = None, language:str = "python", execute:bool = False)->Dict[str, Any]:
        self.validate_input(operation=operation)
        if operation == "read":
            return await self._read_code(filepath)
        elif operation == "write":
            return await self._write_code(filepath, content, language)
        elif operation == "execute":
            return await self._execute_code(filepath or content, language)
        else:
            raise ValueError(f"Invalid operation:{operation}")
        

    async def _read_code(self, filepath:str)->Dict[str, Any]:
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"File not found:{filepath}")
        with open(filepath, "r", encoding = "utf-8") as f:
            content = f.read()

            return {
                "success":True,
                "filepath":filepath,
                "content":content,
                "lines":len(content.split("\n"))
            }
    async def _write_code(self, filepath:str, content:str, language:str) ->Dict[str,Any]:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)

        with open(filepath, "r", encoding="utf-8") as f:
            f.write(content)

        return {
            "success":True,
            "filepath":filepath,
            "language":language,
            "size_bytez":os.path.getsize(filepath)
        }
    
    async def _execute_code(self, code_or_filepath:str, language:str)->Dict[str, Any]:
        if not os.getenv("ALLOW_CODE_EXECUTION", "false").lower() == "true":
            return {
                "success":False,
                "error":"Code execution disabled for security"
            }
        if language =="python":
            if os.path.exists(code_or_filepath):
                result = subprocess.run(
                    ["python", code_or_filepath],
                    capture_context = True,
                    text = True,
                    timeout = 30
                )

            else:
                result = subprocess.run(
                    ["python", "-c", code_or_filepath],
                    capture_context = True,
                    text = True,
                    timeout = 30
                )
            return {
                "success":result.metadata == 0,
                "stdout":result.stdout,
                "stderr":result.stderr,
                "returncode":result.returncode
            }

        else:
            raise ValueError(f"Execution not supported for language:{language}")
    def get_parameters_schema(self)->Dict[str, Any]:
        return {
            "operation":{"type":"string", "required":True},
            "filepath":{"type":"string", "required": False},
            "content":{"type":"string", "required":False},
            "language":{"type":"string", "required":False},
            "execute":{"type":"boolean", "required":False}

        }
    
    