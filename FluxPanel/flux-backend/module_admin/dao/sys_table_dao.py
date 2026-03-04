# -*- coding:utf-8 -*-

from typing import List
from datetime import datetime, time
from sqlalchemy import and_, delete, desc, func, or_, select, update, text
from sqlalchemy.ext.asyncio import AsyncSession
from module_admin.entity.do.dept_do import SysDept
from module_admin.entity.do.sys_table_do import SysTable
from module_admin.entity.vo.sys_table_vo import SysTablePageModel, SysTableModel, DbTablePageModel
from module_gen.entity.vo.gen_table_vo import GenTablePageModel, GenTableModel
from utils.page_util import PageUtil, PageResponseModel


class SysTableDao:

    @classmethod
    async def get_by_id(cls, db: AsyncSession, sys_table_id: int) -> SysTable:
        """根据主键获取单条记录"""
        sys_table = (((await db.execute(
                            select(SysTable)
                            .where(SysTable.id == sys_table_id)))
                       .scalars())
                       .first())
        return sys_table

    """
    查询
    """
    @classmethod
    async def get_sys_table_list(cls, db: AsyncSession,
                             query_object: SysTablePageModel,
                             is_page: bool = False) -> [list | PageResponseModel]:

        query = (
            select(SysTable)
            .where(
                SysTable.field_name.like(f"%{query_object.field_name}%") if query_object.field_name else True,
                SysTable.prop.like(f"%{query_object.prop}%") if query_object.prop else True,
                SysTable.table_name == query_object.table_name if query_object.table_name else True,
                SysTable.del_flag == '0'
            )
            .order_by(SysTable.table_name, SysTable.sequence)
            .distinct()
        )
        sys_table_list = await PageUtil.paginate(db, query, query_object.page_num, query_object.page_size, is_page)
        return sys_table_list


    @classmethod
    async def add_sys_table(cls, db: AsyncSession, add_model: SysTableModel, auto_commit: bool = True) -> SysTable:
        """
        增加
        """
        sys_table = SysTable(**add_model.model_dump(exclude_unset=True))
        db.add(sys_table)
        await db.flush()
        if auto_commit:
            await db.commit()
        return sys_table

    @classmethod
    async def edit_sys_table(cls, db: AsyncSession, edit_model: SysTableModel, auto_commit: bool = True) -> SysTable:
        """
        修改
        """
        edit_dict_data = edit_model.model_dump(exclude_unset=True)
        await db.execute(update(SysTable), [edit_dict_data])
        await db.flush()
        if auto_commit:
            await db.commit()
        return await cls.get_by_id(db, edit_model.id)

    @classmethod
    async def del_sys_table(cls, db: AsyncSession, sys_table_ids: List[str], soft_del: bool = True, auto_commit: bool = True):
        """
        删除
        """
        if soft_del:
            await db.execute(update(SysTable).where(SysTable.id.in_(sys_table_ids)).values(del_flag='2'))
        else:
            await db.execute(delete(SysTable).where(SysTable.id.in_(sys_table_ids)))
        await db.flush()
        if auto_commit:
            await db.commit()



 # 定义查询方法
    @classmethod
    async def select_db_table_list(cls, session: AsyncSession, gen_table: DbTablePageModel, is_page = False) -> PageResponseModel:
        """
        查询数据库中的表信息，根据 GenTable 入参动态添加过滤条件。
        """
        """查询数据库表列表"""
        query = (
            select(
                text("table_name"),
                text("table_comment"),
                text("create_time"),
                text("update_time"),
            )
            .select_from(text("information_schema.tables"))
            .where(
                and_(
                    text("table_schema = (select database())"),
                    text("table_name NOT LIKE 'qrtz\\_%'"),
                    text("table_name NOT LIKE 'apscheduler\\_%'"),
                    text("table_name NOT LIKE 'gen\\_%'"),
                    text("table_name NOT LIKE 'sys\\_%'"),
                    text("table_name NOT IN (select table_name from sys_table)"),
                )
            )
        )
        # 动态条件构造
        if gen_table.table_name:
            query = query.where(
                text("lower(table_name) like lower(:table_name)")
            )
        if gen_table.table_comment:
            query = query.where(
                text("lower(table_comment) like lower(:table_comment)")
            )
        # 排序
        query = query.order_by(text("create_time DESC"))
        # 参数绑定
        params = {}
        if gen_table.table_name:
            params["table_name"] = f"%{gen_table.table_name}%"
        if gen_table.table_comment:
            params["table_comment"] = f"%{gen_table.table_comment}%"

        rows = await PageUtil.paginate(session, query.params(**params), gen_table.page_num, gen_table.page_size, is_page)
        return rows


    @classmethod
    async def select_db_table_list_by_names(cls, session: AsyncSession, table_names: List[str]):
        """根据表名称查询数据库表信息"""
        table_str = ",".join([f"'{item}'" for item in table_names])
        if not table_names:
            return []
        query = select(
            text("table_name"),
            text("table_comment"),
            text("create_time"),
            text("update_time"),
        ).select_from(text('information_schema.tables')).where(
            and_(
                text("table_name NOT LIKE 'qrtz\\_%'"),
                text("table_name NOT LIKE 'apscheduler\\_%'"),
                text("table_name NOT LIKE 'gen\\_%'"),
                text("table_name NOT LIKE 'sys\\_%'"),
                text("table_name NOT IN (select table_name from sys_table)"),
                text(f"table_name IN ({ table_str })"),
                text("table_schema = (select database())")
            )
        )

        result = await session.execute(query)
        rows = result.fetchall()
        # return CamelCaseUtil.transform_result(rows)
        return [
            GenTableModel(tableName=row[0], tableComment=row[1], createTime=row[2], updateTime=row[3]) for row in rows
        ]

    @classmethod
    async def get_sys_table_list_by_ids(cls,  db: AsyncSession, column_ids: List[int]):

        sys_table_columns = (((await db.execute(
            select(SysTable)
            .where(SysTable.id.in_(column_ids))))
                      .scalars())
                     .all())
        return sys_table_columns
