import json

from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from config.database import Base
from config.get_db import get_db
import logging

from module_admin.entity.do.car_driver_do import CarDriver
from module_admin.entity.do.student_info_do import StudentInfo

class TableTool:

    logger = logging.getLogger(__name__)
    # 因为mcp服务是在另外进程里面，需要导入模型，否则Base.registry.mappers是空的
    support_modules = [CarDriver, StudentInfo]

    @classmethod
    async def fetch_table_data(cls, table_name: str) -> str:
        async for query_db in get_db():
            for mapper in Base.registry.mappers:
                table_cls = mapper.class_
                if hasattr(table_cls, '__tablename__') and table_cls.__tablename__ == table_name:
                    result = await query_db.execute(select(table_cls))
                    data = result.scalars().all()
                    json_str = json.dumps(jsonable_encoder(data), ensure_ascii=False)
                    return json_str
            raise ValueError(f"No model found for table name: {table_name}，to check if you have imported it")


