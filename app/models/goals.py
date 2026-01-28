from sqlalchemy import Column, String, DateTime, JSON, Text
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
import uuid

from ..database import Base

class Goal(Base):
    __tablename__="goals"
    id = Column(String, primary_key=True, default = lambda:str(uuid.uuid4()))
    description = Column(Text, nullable = False)
    context = Column(JSON, default={})
    priority = Column(String, default ="medium")
    status = Column(String, default ="pending")
    result = Column(JSON, nullable = True)

    created_at = Column(DateTime, default = datetime.now())
    updated_at = Column(DateTime, default = datetime.now())

    def __repr__(self):
        return f"<Goal(id = {self.id}, status = {self.status}, description = {self.description[:50]}>)"
