import os
from sqlalchemy import Column, String, Integer, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from spruned import settings

Base = declarative_base()


class Header(Base):
    __tablename__ = 'headers'
    id = Column(Integer, primary_key=True)
    blockheight = Column(Integer, index=True, unique=True)
    blockhash = Column(String, index=True, unique=True)
    data = Column(String)


if settings.SQLITE_DBNAME:
    engine = create_engine('sqlite:///' + settings.SQLITE_DBNAME)
    if not os.path.exists(settings.SQLITE_DBNAME):
        Base.metadata.create_all(engine)

    session = sessionmaker()
    session.configure(bind=engine)
