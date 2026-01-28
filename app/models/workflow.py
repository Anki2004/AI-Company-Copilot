from sqlalchemy import Column, String, DateTime, JSON, Boolean, ForeignKey, Integer
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

from ..database import Base

class Workflow(Base):
    __tablename__ = "workflows"

    id = Column(String, primary_key=True, default = lambda:str(uuid.uuid4()))
    goal_id = Column(String, ForeignKey("goals.id"), nullable=False)

    status = Column(String, default = "planning")
    current_task_id = Column(String, nullable = True)

    approval_needed = Column(Boolean, default = False)
    approval_context = Column(JSON, nullable = False)

    total_tasks = Column(Integer, default = 0)
    completed_tasks = Column(Integer, default = 0)

    created_at = Column(DateTime, default = datetime.now())
    updated_at = Column(DateTime, default = datetime.now(), onupdate = datetime.now())


    tasks = relationship("Task", back_populates = "workflow", cascade = "all, delete-orphan")


    def __repr__(self):
        return f"<Workflow(id={self.id}, goal_id={self.goal_id}, status={self.status})>"
