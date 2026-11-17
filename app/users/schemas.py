from datetime import datetime

from pydantic import BaseModel, ConfigDict


class UserCreate(BaseModel):
    telegram_id: int
    username: str | None = None
    nickname: str = ""
    premium: bool = False


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    telegram_id: int
    username: str | None
    nickname: str
    premium: bool
    created_at: datetime
    updated_at: datetime


class UserStats(BaseModel):
    total: int
    new_today: int
