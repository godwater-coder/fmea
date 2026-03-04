# -*- coding:utf-8 -*-

from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from utils.common_util import CamelCaseUtil, export_list2excel
from utils.page_util import PageResponseModel
from module_admin.dao.sys_form_dao import SysFormDao
from module_admin.entity.do.sys_form_do import SysForm
from module_admin.entity.vo.sys_form_vo import SysFormPageModel, SysFormModel


class SysFormService:
    """
    用户管理模块服务层
    """

    @classmethod
    async def get_sys_form_list(cls, query_db: AsyncSession, query_object: SysFormPageModel, data_scope_sql: str) -> [list | PageResponseModel]:
        sys_form_list = await SysFormDao.get_sys_form_list(query_db, query_object, data_scope_sql, is_page=True)
        return sys_form_list

    @classmethod
    async def get_sys_form_by_id(cls, query_db: AsyncSession, sys_form_id: int) -> SysFormModel:
        sys_form = await  SysFormDao.get_by_id(query_db, sys_form_id)
        sys_form_model = SysFormModel(**CamelCaseUtil.transform_result(sys_form))
        return sys_form_model


    @classmethod
    async def add_sys_form(cls, query_db: AsyncSession, query_object: SysFormModel) -> SysFormModel:
        sys_form = await SysFormDao.add_sys_form(query_db, query_object)
        sys_form_model = SysFormModel(**CamelCaseUtil.transform_result(sys_form))
        return sys_form_model


    @classmethod
    async def update_sys_form(cls, query_db: AsyncSession, query_object: SysFormModel) -> SysFormModel:
        sys_form = await SysFormDao.edit_sys_form(query_db, query_object)
        sys_form_model = SysFormModel(**CamelCaseUtil.transform_result(sys_form))
        return sys_form_model


    @classmethod
    async def del_sys_form(cls, query_db: AsyncSession, sys_form_ids: List[str]):
        await SysFormDao.del_sys_form(query_db, sys_form_ids)


    @classmethod
    async def export_sys_form_list(cls, query_db: AsyncSession, query_object: SysFormPageModel, data_scope_sql) -> bytes:
        sys_form_list = await SysFormDao.get_sys_form_list(query_db, query_object, data_scope_sql, is_page=False)
        mapping_dict = {
            'createTime': '创建时间 ',
            'generateConf': '生成配置 ',
            'name': '表单名称 ',
            'updateTime': '更新时间 ',
        }
        new_data = [
            {mapping_dict.get(key): value for key, value in item.items() if mapping_dict.get(key)} for item in sys_form_list
        ]
        binary_data = export_list2excel(new_data)
        return binary_data