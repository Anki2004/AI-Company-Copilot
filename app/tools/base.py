from abc import ABC, abstractmethod
from typing import Dict,Any

class BaseTool(ABC):

    def __init__(self):
        self.name:str = ""
        self.description:str = ""
        self.category:str = ""

    @abstractmethod
    async def execute(self, **kwargs)-> Dict[str,Any]:
        raise NotImplementedError("Subclasses must be implement execute()")
    
    @abstractmethod
    async def get_paramters_schema(self)->Dict[str, Any]:
        raise NotImplementedError("Subclasses must be implement get_parameters_schema()")
    

    def validate_input(self, **kwargs):
        schema = self.get_paramters_schema()
        for param, spec in schema.items():
            if spec.get("required", False) and param not in kwargs:
                raise ValueError(f"Missing required parameter:{param}")
            

