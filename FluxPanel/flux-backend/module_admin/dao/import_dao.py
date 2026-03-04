from typing import List, Dict

from sqlalchemy import text, Table, insert
from sqlalchemy.ext.asyncio import AsyncSession

from module_admin.entity.vo.import_vo import ImportFieldModel
from module_gen.entity.vo.gen_table_column_vo import GenTableColumnModel


class ImportDao:
    """
    字典类型管理模块数据库操作层
    """

    @classmethod
    async def select_table_columns_by_name(cls, session: AsyncSession, table_name: str) -> List[GenTableColumnModel]:
        """
        查询指定表的列信息。
        :param session: AsyncSession 数据库会话
        :param table_name: 表名
        :return: 查询结果映射到 GenTableColumnResult 对象的列表
        """
        # 检查表名是否为空
        if not table_name:
            raise ValueError("Table name cannot be empty.")

        # 基础查询
        query = text("""
                       SELECT column_name,
                              (CASE WHEN (is_nullable = 'no' AND column_key != 'PRI') THEN '1' ELSE '0' END) AS is_required,
                              (CASE WHEN column_key = 'PRI' THEN '1' ELSE '0' END) AS is_pk,
                              ordinal_position AS sort,
                              column_comment,
                              (CASE WHEN extra = 'auto_increment' THEN '1' ELSE '0' END) AS is_increment,
                              column_type
                       FROM information_schema.columns
                       WHERE table_schema = (SELECT DATABASE())
                       AND table_name = :table_name
                       ORDER BY ordinal_position
                   """)

        # 执行查询并传递参数
        result = await session.execute(query, {"table_name": table_name})
        rows = result.fetchall()
        # 将结果映射到 GenTableColumnResult 对象
        return [
            GenTableColumnModel(
                columnName=row[0],
                isRequired=row[1],
                isPk=row[2],
                sort=row[3],
                columnComment=row[4],
                isIncrement=row[5],
                columnType=row[6]
            ) for row in rows
        ]

    @classmethod
    async def import_data(cls, session: AsyncSession, table_name: str, field_list: list, value_list: list):
        """
        批量插入数据到数据库
        :param session: db session
        :param table_name: 数据库表名
        :param field_list: 字段名列表
        :param value_list: 多行数据，每一项是字段对应的值（列表）
        """
        if not field_list or not value_list:
            raise ValueError("field_list 和 value_lists 不能为空")
        if not all(len(field_list) == len(values) for values in value_list):
            raise ValueError("field_list 和 value_lists 的长度必须一致")
        # 构造 SQL 语句
        field_str = ", ".join(field_list)
        value_placeholders = ", ".join([f":{field}" for field in field_list])
        sql = f"INSERT INTO {table_name} ({field_str}) VALUES ({value_placeholders})"
        # 构造参数列表
        values_dicts = [{field: value for field, value in zip(field_list, values)} for values in value_list]
        # 批量执行 SQL
        await session.execute(text(sql), values_dicts)
        await session.flush()
        await session.commit()
