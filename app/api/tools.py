from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from ..tools import get_all_tools, get_tools_by_name

router = APIRouter(prefix="/api/tools", tags=["tools"])

class ToolSchema(BaseModel):
    name:str
    description:str
    parameters:Dict[str, Any]
    category:str

class ToolResponse(BaseModel):
    tools:List[ToolSchema]


@router.get("/", response_model = ToolResponse)
async def list_tools():
    tools = get_all_tools()
    tool_schema = [
        ToolSchema(
            name=tool.name,
            description = tool.description,
            paramters = tool.get_parameter_schema(),
            category = tool.category

        )for tool in tools
    ]
    return ToolResponse(tools = tool_schema)

class ToolExecuteRequest(BaseModel):
    tool_name:str
    parameters:dict

@router.post("/execute")
async def execute_tool(request:ToolExecuteRequest):
    try:
        tool = get_tools_by_name(request.tool_name)
        if not tool:
            raise HTTPException(status_code=404, detail=f"Tool '{request.tool_name}' not found")
        result = await tool.execute(**request.parameters)

        return {
            "status":"success",
            "tool":request.tool_name,
            "result":result
        }
    except Exception  as e:
        raise HTTPException(status_code = 500, detail=f"Tool execution failed:{str(e)}")


