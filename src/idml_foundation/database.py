import sqlite3
from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from idml_foundation.settings import Settings, get_settings


class Base(DeclarativeBase):
    pass


def ensure_write_transaction(db: Session) -> None:
    """Make SQLite savepoints subordinate to the caller's real transaction."""
    connection = db.connection()
    if connection.dialect.name == "sqlite":
        driver = connection.connection.driver_connection
        if not isinstance(driver, sqlite3.Connection):
            raise RuntimeError("unsupported_sqlite_transaction_driver")
        if not driver.in_transaction:
            connection.exec_driver_sql("BEGIN IMMEDIATE")


def create_database_engine(settings: Settings | None = None) -> Engine:
    config = settings or get_settings()
    kwargs: dict[str, object] = {"pool_pre_ping": True}
    if config.database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    return create_engine(config.database_url, **kwargs)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


engine = create_database_engine()
SessionLocal = create_session_factory(engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@contextmanager
def session_scope(factory: sessionmaker[Session] = SessionLocal) -> Generator[Session, None, None]:
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
