from sqlalchemy import create_engine
from sqlalchemy.ext.declaratie import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
import os


DATABASE_URL = os.getenv("DATABASE_URL", "")
engine = create_engine(
    DATABASE_URL,
    poolclass = StaticPool,
    echo = True
)

SessionLocal = sessionmaker(autocommit = False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db=SessionLocal()
    try:
        yield db
    finally:
        db.close()
def init_db():
    Base.metadata.create_all(bind=engine)


    