from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from . import config

config.DATA_DIR.mkdir(parents=True, exist_ok=True)
engine = create_engine(f"sqlite:///{config.DB_PATH}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


def init_db():
    from . import models  # noqa: F401  (đăng ký model trước khi tạo bảng)
    Base.metadata.create_all(bind=engine)
