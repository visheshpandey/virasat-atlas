"""Public view of a user."""
import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr


class UserOut(BaseModel):
    id: uuid.UUID
    name: str
    email: EmailStr
    phone: str | None
    role: str
    created_at: datetime

    model_config = {"from_attributes": True}
