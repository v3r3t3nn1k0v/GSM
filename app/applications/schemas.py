from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.applications.models import ApplicationStatus


class ApplicationCreate(BaseModel):
    user_id: int


class ApplicationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    status: ApplicationStatus
    fuel_type: str | None
    gas_networks: str | None
    monthly_volume: str | None
    region: str | None
    delivery_needed: str | None
    full_name: str | None
    phone: str | None
    reminders_sent: int
    last_reminder_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ApplicationStats(BaseModel):
    total: int
    partly_filled: int
    filled: int
    processed: int
