import datetime

from sqlalchemy import Column, Integer, DateTime, String, text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase
from urllib.parse import quote_plus
from config.env import DataBaseConfig

ASYNC_SQLALCHEMY_DATABASE_URL = (
    f'mysql+asyncmy://{DataBaseConfig.db_username}:{quote_plus(DataBaseConfig.db_password)}@'
    f'{DataBaseConfig.db_host}:{DataBaseConfig.db_port}/{DataBaseConfig.db_database}'
)
if DataBaseConfig.db_type == 'postgresql':
    ASYNC_SQLALCHEMY_DATABASE_URL = (
        f'postgresql+asyncpg://{DataBaseConfig.db_username}:{quote_plus(DataBaseConfig.db_password)}@'
        f'{DataBaseConfig.db_host}:{DataBaseConfig.db_port}/{DataBaseConfig.db_database}'
    )

async_engine = create_async_engine(
    ASYNC_SQLALCHEMY_DATABASE_URL,
    echo=DataBaseConfig.db_echo,
    max_overflow=DataBaseConfig.db_max_overflow,
    pool_size=DataBaseConfig.db_pool_size,
    pool_recycle=DataBaseConfig.db_pool_recycle,
    pool_timeout=DataBaseConfig.db_pool_timeout,
)
AsyncSessionLocal = async_sessionmaker(autocommit=False, autoflush=False, bind=async_engine)


class Base(AsyncAttrs, DeclarativeBase):
    pass

class BaseMixin:
    """model的基类,所有model都必须继承"""
    id = Column(Integer, primary_key=True, autoincrement=True)
    create_time = Column(DateTime, nullable=False, default=datetime.datetime.now, comment='创建时间')
    update_time = Column(DateTime, nullable=False, default=datetime.datetime.now,
                         onupdate=datetime.datetime.now, index=True, comment='更新时间')
    del_flag = Column(String(1), nullable=False, default='0', server_default=text("'0'"), comment='删除标志（0代表存在 2代表删除）')
    create_by = Column(Integer, nullable=False, comment='创建者')
    dept_id = Column(Integer, nullable=False, comment='部门id')