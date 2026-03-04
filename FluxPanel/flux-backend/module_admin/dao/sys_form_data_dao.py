# -*- coding:utf-8 -*-

from typing import List
from datetime import datetime, time
from module_admin.entity.do.role_do import SysRoleDept
from sqlalchemy import and_, delete, desc, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from module_admin.entity.do.sys_form_data_do import SysFormData
from module_admin.entity.vo.sys_form_data_vo import SysFormDataPageModel, SysFormDataModel
from utils.page_util import PageUtil, PageResponseModel


class SysFormDataDao:

    @classmethod
    async def get_by_id(cls, db: AsyncSession, sys_form_data_id: int) -> SysFormData:
        """根据主键获取单条记录"""
        sys_form_data = (((await db.execute(
                            select(SysFormData)
                            .where(SysFormData.id == sys_form_data_id)))
                       .scalars())
                       .first())
        return sys_form_data

    """
    查询
    """
    @classmethod
    async def get_sys_form_data_list(cls, db: AsyncSession,
                             query_object: SysFormDataPageModel,
                             data_scope_sql: str = None,
                             is_page: bool = False) -> [list | PageResponseModel]:

        query = (
            select(SysFormData)
            .where(
                SysFormData.form_data == query_object.form_data if query_object.form_data else True,
                SysFormData.form_id == query_object.form_id if query_object.form_id else True,
                SysFormData.form_name == query_object.form_name if query_object.form_name else True,
                SysFormData.del_flag == '0',
                eval(data_scope_sql) if data_scope_sql else True,
            )
            .order_by(desc(SysFormData.create_time))
            .distinct()
        )
        sys_form_data_list = await PageUtil.paginate(db, query, query_object.page_num, query_object.page_size, is_page)
        return sys_form_data_list


    @classmethod
    async def add_sys_form_data(cls, db: AsyncSession, add_model: SysFormDataModel, auto_commit: bool = True) -> SysFormData:
        """
        增加
        """
        sys_form_data =  SysFormData(**add_model.model_dump(exclude_unset=True))
        db.add(sys_form_data)
        await db.flush()
        if auto_commit:
            await db.commit()
        return sys_form_data

    @classmethod
    async def edit_sys_form_data(cls, db: AsyncSession, edit_model: SysFormDataModel, auto_commit: bool = True) -> SysFormData:
        """
        修改
        """
        edit_dict_data = edit_model.model_dump(exclude_unset=True)
        await db.execute(update(SysFormData), [edit_dict_data])
        await db.flush()
        if auto_commit:
            await db.commit()
        return await cls.get_by_id(db, edit_model.id)

    @classmethod
    async def del_sys_form_data(cls, db: AsyncSession, sys_form_data_ids: List[str], soft_del: bool = True, auto_commit: bool = True):
        """
        删除
        """
        if soft_del:
            await db.execute(update(SysFormData).where(SysFormData.id.in_(sys_form_data_ids)).values(del_flag='2'))
        else:
            await db.execute(delete(SysFormData).where(SysFormData.id.in_(sys_form_data_ids)))
        await db.flush()
        if auto_commit:
            await db.commit()