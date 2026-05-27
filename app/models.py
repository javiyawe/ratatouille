from typing import Optional
from pydantic import BaseModel

class SearchRequest(BaseModel):
    query: str
    n_results: int = 6
    max_time: Optional[int] = None
    difficulty: Optional[str] = None

class ChatRequest(BaseModel):
    message: str
    chat_id: Optional[str] = None

class ChatSessionCreate(BaseModel):
    title: str = "Nueva conversación"

class ExtractRequest(BaseModel):
    text: str

class SaveRecipeRequest(BaseModel):
    recipe: dict

class UpdateRecipeRequest(BaseModel):
    recipe: dict

class RefineRecipeRequest(BaseModel):
    recipe: dict
    instructions: str

class MCPCallRequest(BaseModel):
    tool: str
    params: dict = {}

class UpdateChatTitleRequest(BaseModel):
    title: str

class TrainingCompareRequest(BaseModel):
    question: str
