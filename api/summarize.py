from pydantic import BaseModel

class SummarizeRequest(BaseModel):
    file_name: str
    category: str
    user_id: str