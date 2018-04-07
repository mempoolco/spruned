import plyvel
from sqlalchemy import Column, String, Integer, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, scoped_session
import threading
from functools import wraps
from spruned import settings

Base = declarative_base()


class Header(Base):
    __tablename__ = 'headers'
    id = Column(Integer, primary_key=True)
    blockheight = Column(Integer, index=True, unique=True)
    blockhash = Column(String, index=True, unique=True)
    data = Column(String)


engine = create_engine('sqlite:///' + settings.SQLITE_DBNAME)
Base.metadata.create_all(engine)

sqlite = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=engine))

if not settings.TESTING:
    storage_ldb = plyvel.DB(settings.LEVELDB_BLOCKCHAIN_ADDRESS, create_if_missing=True)
else:
    from unittest.mock import Mock
    storage_ldb = Mock()

_local = threading.local()
_local.session = sqlite
_local.storage_ldb = storage_ldb


def atomic(fun):
    @wraps(fun)
    def decorator(*args, **kwargs):
        try:
            try:
                _local.counter += 1
            except AttributeError:
                _local.counter = 1
            r = fun(*args, **kwargs)
            if _local.counter == 1:
                _local.session.commit()
                _local.counter -= 1
            return r
        except Exception as e:
            if _local.counter == 1:
                _local.session.rollback()
                _local.counter -= 1
            raise e
        finally:
            _local.session.close()
    return decorator


def ldb_batch(fun):
    @wraps(fun)
    def decorator(*args, **kwargs):
        try:
            _local.leveldb_counter += 1
        except AttributeError:
            _local.leveldb_counter = 1
        if _local.leveldb_counter == 1:
            try:
                if not _local.in_ldb_batch:
                    _local.storage_ldb = storage_ldb.write_batch()
                    _local.in_ldb_batch = True
            except AttributeError:
                _local.in_ldb_batch = True
                _local.storage_ldb = storage_ldb.write_batch()
        r = fun(*args, **kwargs)
        if _local.leveldb_counter == 1:
            _local.storage_ldb.write()
            if _local.in_ldb_batch:
                _local.in_ldb_batch = False
                del _local.storage_ldb
                _local.storage_ldb = storage_ldb
        _local.leveldb_counter -= 1
        return r
    return decorator
