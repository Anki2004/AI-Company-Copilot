from typing import Dict, Any, Optional
from .base import BaseTool

class ApprovalTool(BaseTool):
    def __init__(self):
        super().__init__()
        self.name = "approval"
        self.description = "Request human approval with context"
        self.category = "workflow"

    async def execute(self, context:Any, message:str = "Please review and approve")->Dict[str, Any]:
        return {
            "approval_required":True,
            "message":message,
            "context":context,
            "timestamp":__import__("datetime").datetime.now().isoformat()
        }
    def get_parameters_schema(self)->Dict[str, Any]:
        return {
            "context":{"type":"any","required":True},
            "message":{"type":"string", "required":False}
        }
    