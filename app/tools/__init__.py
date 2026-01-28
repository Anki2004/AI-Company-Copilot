from typing import List, Optional
from .base import BaseTool
from .search import SearchTool
from .extract import ExtractTool
from .write import WriteTool
from .update import UpdateTool
from .code import CodeTool

from .approval import ApprovalTool


_TOOL_REGISTRY_=[
    SearchTool(),
    BaseTool(),
    ExtractTool(),
    CodeTool(),
    UpdateTool(),
    ApprovalTool(),
    WriteTool()

]

def get_all_tools()->List[BaseTool]:
    return _TOOL_REGISTRY_

def get_tool_by_name(name:str)->Optional[BaseTool]:
    for tool in _TOOL_REGISTRY_:
        if tool.name == name:
            return tool
    return None


__all__=[
    "BaseTool",
    "SearchTool",
    "ExtractTool",
    "WriteTool",
    "UpdateTool",
    "CodeTool",
    "ApprovalTool",
    "get_all_tools",
    "get_tool_by_name"
]