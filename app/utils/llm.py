import os
from typing import List, Dict, Any, Optional
import anthropic

class LLMClient:
    def __init__(self):
        self.client =anthropic.Anthropic(
            api_key = os.getenv("ANTHROPIC_API_KEY"),

        )
        self.model = "claude-sonnet-4-20250514"

    async def comlete(self, prompt:str, system:Optional[str]=None, max_tokens:int=4096)->str:
        messages = [{"role":"user", "content":prompt}]

        response = self.client.messages.create(
            model = self.model,
            max_tokens = max_tokens,
            messages = messages,
            system = system if system else "You are a helpful AI Assistant"
        )

        return response.content[0].text

    async def complete_with_tools(self, prompt:str, tools:List[Dict[str, Any]], system:Optional[str]=None, max_tokens:int=4096)->Dict[str, Any]:
        messages = [{"role":"user", "content":prompt}]
        response = self.client.messages.create(
            model = self.model,
            max_tokens = max_tokens,
            messages = messages,
            tools = tools,
            system = system if system else "You are a helpful AI Assistant."
        )

        text_content = []
        tool_calls = []
        for block in response.content:
            if block.type == "text":
                text_content.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append({
                    "id":block.id,
                    "name":block.name,
                    "input":block.input
                })

        return {
            "text":"\n".join(text_content),
            "tool_calls":tool_calls,
            "stop_reason":response.stop_reason
        }


    async def continue_conersation(self, messages:List[Dict[str, Any]], tools:List[Dict[str, Any]], system:Optional[str] = None)->Dict[str, Any]:
        response = self.client.messages.create(
            model = self.model,
            max_tokens = 4096,
            messages = messages,
            tools = tools,
            system = system if system else "You are a helpful AI Assitant."
        )

        text_content = []
        tool_calls =[]
        for block in response.content:
            if block.type == "text":
                text_content.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append({
                    "id":block.id,
                    "name":block.name,
                    "input":block.input
                })

        return {
            "text":"\n".join(text_content),
            "tool_calls":tool_calls,
            "stop_reason":response.stop_reason
        }
