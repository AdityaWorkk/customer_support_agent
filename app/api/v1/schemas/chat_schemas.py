from pydantic import BaseModel, Field


class MessageIn(BaseModel):
    content: str = Field(min_length=1, max_length=2000)
    attachment_id: str | None = Field(default=None, max_length=64)


class ConfirmIn(BaseModel):
    approved: bool


class AdminMessageIn(BaseModel):
    content: str = Field(min_length=1, max_length=2000)
