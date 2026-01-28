from sqlalchemy import Column, String, Integer, JSON, ForeignKey, Text, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

from ..database import Base


class Task(Base):
    __tablename__= "tasks"

    id = Column(String, primary_key=True, default = lambda:str(uuid.uuid4()))
    workflow_id = Column(String, ForeignKey("workflow.id"), nullable=False)

    tool_name = Column(String, nullable = False)
    decription = Column(Text, nullable = True)
    order = Column(Integer, nullable=False)

    status = Column(String, default = "pending")
    input_data = Column(JSON, nullable = False)
    output_data = Column(JSON, nullable = True)
    error = Column(Text, nullable = True)

    dependencies = Column(JSON, default = [])

    started_at = Column(DateTime, nullable = True)
    created_at = Column(DateTime, nullable = True)

    updated_at = Column(DateTime, default = datetime.now())

    workflow = relationship("Workflow", back_populates = "tasks")


    def __repr__(self):
        return f"<Task(id={self.id}, tool={self.tool_name},status = {self.status})>"

        


