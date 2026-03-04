# -*- coding:utf-8 -*-
import json
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession

from exceptions.exception import ServiceException
from module_admin.dao.sys_form_dao import SysFormDao
from module_admin.entity.vo.sys_form_vo import SysFormPageModel
from utils.common_util import CamelCaseUtil, export_list2excel
from utils.page_util import PageResponseModel
from module_admin.dao.sys_form_data_dao import SysFormDataDao
from module_admin.entity.do.sys_form_data_do import SysFormData
from module_admin.entity.vo.sys_form_data_vo import SysFormDataPageModel, SysFormDataModel


class SysFormDataService:
    """
    用户管理模块服务层
    """

    @classmethod
    async def get_sys_form_data_list(cls, query_db: AsyncSession, query_object: SysFormDataPageModel, data_scope_sql: str|None) -> [list | PageResponseModel]:
        sys_form_data_list = await SysFormDataDao.get_sys_form_data_list(query_db, query_object, data_scope_sql, is_page=True)
        return sys_form_data_list

    @classmethod
    async def get_sys_form_data_by_id(cls, query_db: AsyncSession, sys_form_data_id: int) -> SysFormDataModel:
        sys_form_data = await  SysFormDataDao.get_by_id(query_db, sys_form_data_id)
        sys_form_data_model = SysFormDataModel(**CamelCaseUtil.transform_result(sys_form_data))
        return sys_form_data_model


    @classmethod
    async def add_sys_form_data(cls, query_db: AsyncSession, query_object: SysFormDataModel) -> SysFormDataModel:
        sys_form = await SysFormDao.get_by_name(query_db, query_object.form_name)
        if sys_form is None:
            raise ServiceException(message=f"未查询到该表单【{query_object.form_name}】")
        elif len(sys_form) > 1:
            raise ServiceException(message=f"存在表单【{query_object.form_name}】{len(sys_form)}份， 无法保存")
        # 拿到ID
        query_object.form_id = sys_form[0].id
        sys_form_data = await SysFormDataDao.add_sys_form_data(query_db, query_object)
        sys_form_data_model = SysFormDataModel(**CamelCaseUtil.transform_result(sys_form_data))
        return sys_form_data_model


    @classmethod
    async def update_sys_form_data(cls, query_db: AsyncSession, query_object: SysFormDataModel) -> SysFormDataModel:
        sys_form_data = await SysFormDataDao.edit_sys_form_data(query_db, query_object)
        sys_form_data_model = SysFormDataModel(**CamelCaseUtil.transform_result(sys_form_data))
        return sys_form_data_model


    @classmethod
    async def del_sys_form_data(cls, query_db: AsyncSession, sys_form_data_ids: List[str]):
        await SysFormDataDao.del_sys_form_data(query_db, sys_form_data_ids)


    @classmethod
    async def export_sys_form_data_list(cls, query_db: AsyncSession, query_object: SysFormDataPageModel, data_scope_sql) -> bytes:
        sys_form_data_list = await SysFormDataDao.get_sys_form_data_list(query_db, query_object, data_scope_sql, is_page=False)

        new_data = []
        for form_data in sys_form_data_list:
            content = form_data['formData']
            content_dict = json.loads(content)
            item = {}
            for key, value in content_dict.items():
                item[key] = value
            new_data.append(item)
        binary_data = export_list2excel(new_data)
        return binary_data