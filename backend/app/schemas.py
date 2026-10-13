from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class Creds(BaseModel):
    email: str = Field(min_length=3, max_length=320, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=10, max_length=256)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: str
    email: str


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    conversation_id: str | None = None
    idempotency_key: str | None = Field(default=None, max_length=64)


class ChatOut(BaseModel):
    conversation_id: str
    task_id: str


class StepOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    index: int
    tool: str
    description: str
    args: dict
    risk: str
    requires_approval: bool
    approved: bool
    status: str
    attempts: int
    output: dict | None
    error: str | None
    started_at: datetime | None
    finished_at: datetime | None


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    conversation_id: str | None
    request: str
    route: str
    status: str
    success_criteria: list
    summary: str | None
    verification: dict | None
    error: str | None
    created_at: datetime
    updated_at: datetime
    steps: list[StepOut]


class TaskListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    request: str
    route: str
    status: str
    created_at: datetime


class Page(BaseModel):
    items: list
    total: int
    limit: int
    offset: int


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    role: str
    content: str
    task_id: str | None
    created_at: datetime


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    title: str
    created_at: datetime


class ConversationDetail(ConversationOut):
    messages: list[MessageOut]


class AuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    action: str
    resource: str
    outcome: str
    detail: dict
    created_at: datetime
