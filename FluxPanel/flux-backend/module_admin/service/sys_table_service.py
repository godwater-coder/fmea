# -*- coding:utf-8 -*-

from typing import List
from sqlalchemy.ext.asyncio import AsyncSession

from module_gen.dao.gen_table_column_dao import GenTableColumnDao
from module_gen.utils.jinja2_tools import snake_to_camel
from utils.common_util import CamelCaseUtil, export_list2excel
from utils.page_util import PageResponseModel
from module_admin.dao.sys_table_dao import SysTableDao
from module_admin.entity.do.sys_table_do import SysTable
from module_admin.entity.vo.sys_table_vo import SysTablePageModel, SysTableModel, DbTablePageModel


class SysTableService:
    """
    用户管理模块服务层
    """

    @classmethod
    async def get_sys_table_list(cls, query_db: AsyncSession, query_object: SysTablePageModel,  is_page=True) -> [list | PageResponseModel]:
        sys_table_list = await SysTableDao.get_sys_table_list(query_db, query_object, is_page=is_page)
        return sys_table_list


    @classmethod
    async def select_db_table_list(cls, gen_table: DbTablePageModel, query_db, data_scope_sql) -> PageResponseModel:
        """查询数据库列表"""
        return await SysTableDao.select_db_table_list(query_db, gen_table, is_page=True)

    @classmethod
    async def get_sys_table_by_id(cls, query_db: AsyncSession, sys_table_id: int) -> SysTableModel:
        sys_table = await  SysTableDao.get_by_id(query_db, sys_table_id)
        sys_table_model = SysTableModel(**CamelCaseUtil.transform_result(sys_table))
        return sys_table_model


    @classmethod
    async def add_sys_table(cls, query_db: AsyncSession, query_object: SysTableModel) -> SysTableModel:
        sys_table = await SysTableDao.add_sys_table(query_db, query_object)
        sys_table_model = SysTableModel(**CamelCaseUtil.transform_result(sys_table))
        return sys_table_model

    @classmethod
    async def import_sys_table(cls, query_db: AsyncSession, tables: [str]):

        tables = await SysTableDao.select_db_table_list_by_names(query_db, tables)
        for table in tables:

            # 查询表列信息
            columns = await GenTableColumnDao.select_db_table_columns_by_name(query_db, table.table_name)
            # 添加列信息
            for i, column in enumerate(columns):
                sys_table = SysTableModel()
                sys_table.table_name = table.table_name
                sys_table.field_name = column.column_name
                sys_table.prop = snake_to_camel(column.column_name)
                sys_table.label = column.column_comment if column.column_comment else column.column_name
                await SysTableDao.add_sys_table(query_db, sys_table, auto_commit=False)
            # 添加操作框
            operate_model = SysTableModel(tableName=table.table_name, fieldName = 'operate',  prop='operate', label='操作', width=200)
            await SysTableDao.add_sys_table(query_db, operate_model, auto_commit=False)
        await query_db.commit()


    @classmethod
    async def update_sys_table(cls, query_db: AsyncSession, query_object: SysTableModel) -> SysTableModel:
        sys_table = await SysTableDao.edit_sys_table(query_db, query_object)
        sys_table_model = SysTableModel(**CamelCaseUtil.transform_result(sys_table))
        return sys_table_model


    @classmethod
    async def del_sys_table(cls, query_db: AsyncSession, sys_table_ids: List[str]):
        await SysTableDao.del_sys_table(query_db, sys_table_ids, soft_del=False)


    @classmethod
    async def export_sys_table_list(cls, query_db: AsyncSession, query_object: SysTablePageModel, data_scope_sql) -> bytes:
        sys_table_list = await SysTableDao.get_sys_table_list(query_db, query_object, data_scope_sql, is_page=False)
        mapping_dict = {
            'align': '对其方式 ',
            'fileldName': '字段名 ',
            'fixed': '固定表头 ',
            'label': '字段标签 ',
            'labelTip': '字段标签解释 ',
            'prop': '驼峰属性 ',
            'show': '可见 ',
            'sortable': '可排序 ',
            'tableName': '表名 ',
            'tooltip': '超出隐藏 ',
            'updateByName': '更新者 ',
            'updateTime': '更新时间 ',
            'width': '宽度 ',
        }
        new_data = [
            {mapping_dict.get(key): value for key, value in item.items() if mapping_dict.get(key)} for item in sys_table_list
        ]
        binary_data = export_list2excel(new_data)
        return binary_data

    @classmethod
    async def sort_column(cls, query_db: AsyncSession, column_ids: List[int]):
        columns = await SysTableDao.get_sys_table_list_by_ids(query_db, column_ids)
        columns_dict = {column.id: column for column in columns}
        for idx, sys_table_id in enumerate(column_ids):
            sys_table_column = columns_dict.get(sys_table_id)
            if sys_table_column:
                sys_table_column.sequence = idx # 顺序从 0 开始
        await query_db.flush()
        await query_db.commit()
