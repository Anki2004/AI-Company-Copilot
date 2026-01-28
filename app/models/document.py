from sqlclahemy import JSON, Column, String, Integer, DateTime, Text
from sqlalchemy.dialects.postgresql import ARRAY
from pgvector.sqlalchemy import Vector
from datetime import datetime
import uuid


from ..database import Base

class Document(Base):
    __tablename__ = "documents"

    id = Column(String, primary_key=True, default = lambda:str(uuid.uuid4()))
    content = Column(Text, nullable = False)
    embedding = Column(Vector(1536))

    source = Column(String, nullable = False)
    source_id =Column(String, nullable= True)
    source_url = Column(String, nullable = True)

    title = Column(String, nullable = True)
    author = Column(String, nullable = True)
    doc_type = Column(String, nullabe = True)

    parent_doc_id = Column(String, nullable = True)
    chunk_index = Column(Integer, nullable = True)

    metadata = Column(JSON, default = {})
    created_at = Column(DateTime, default=datetime.now())
    updated_at = Column(DateTime, default= datetime.now(), onuptime = datetime.now())
    source_at = Column(DateTime, nullable=False)

    def __repr__(self):
        return f"<Document(id={self.id}, title = {self.title}, source={self.source})"



        

