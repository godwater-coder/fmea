# -*- coding:utf-8 -*-

from typing import List, Sequence
from datetime import datetime, time
from module_admin.entity.do.role_do import SysRoleDept
from sqlalchemy import and_, delete, desc, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from module_admin.entity.do.sys_form_data_do import SysFormData
from module_admin.entity.do.sys_form_do import SysForm
from module_admin.entity.vo.sys_form_vo import SysFormPageModel, SysFormModel
from utils.page_util import PageUtil, PageResponseModel


class SysFormDao:

    @classmethod
    async def get_by_id(cls, db: AsyncSession, sys_form_id: int) -> SysForm:
        """根据主键获取单条记录"""
        sys_form = (((await db.execute(
                            select(SysForm)
                            .where(SysForm.id == sys_form_id)))
                       .scalars())
                       .first())
        return sys_form

    @classmethod
    async def get_by_name(cls, db: AsyncSession, sys_form_name: str) -> Sequence[SysForm]:
        """根据主键获取单条记录"""
        sys_form = (((await db.execute(
            select(SysForm)
            .where(SysForm.name == sys_form_name)))
                     .scalars())
                    .all())
        return sys_form

    """
    查询
    """
    @classmethod
    async def get_sys_form_list(cls, db: AsyncSession,
                             query_object: SysFormPageModel,
                             data_scope_sql: str = None,
                             is_page: bool = False) -> [list | PageResponseModel]:

        query = (
            select(*SysForm.__table__.c, func.count(SysFormData.id).label("data_count"))
            .outerjoin(SysFormData, SysForm.id == SysFormData.form_id)
            .where(
                SysForm.name.like(f"%{query_object.name}%") if query_object.name else True,
                SysForm.del_flag == '0',
                eval(data_scope_sql) if data_scope_sql else True,
            )
            .group_by(SysForm.id)
            .order_by(desc(SysForm.create_time))
            .distinct()
        )
        sys_form_list = await PageUtil.paginate(db, query, query_object.page_num, query_object.page_size, is_page)
        return sys_form_list


    @classmethod
    async def add_sys_form(cls, db: AsyncSession, add_model: SysFormModel, auto_commit: bool = True) -> SysForm:
        """
        增加
        """
        sys_form =  SysForm(**add_model.model_dump(exclude_unset=True))
        db.add(sys_form)
        await db.flush()
        if auto_commit:
            await db.commit()
        return sys_form

    @classmethod
    async def edit_sys_form(cls, db: AsyncSession, edit_model: SysFormModel, auto_commit: bool = True) -> SysForm:
        """
        修改
        """
        edit_dict_data = edit_model.model_dump(exclude_unset=True)
        await db.execute(update(SysForm), [edit_dict_data])
        await db.flush()
        if auto_commit:
            await db.commit()
        return await cls.get_by_id(db, edit_model.id)

    @classmethod
    async def del_sys_form(cls, db: AsyncSession, sys_form_ids: List[str], soft_del: bool = True, auto_commit: bool = True):
        """
        删除
        """
        if soft_del:
            await db.execute(update(SysForm).where(SysForm.id.in_(sys_form_ids)).values(del_flag='2'))
        else:
            await db.execute(delete(SysForm).where(SysForm.id.in_(sys_form_ids)))
        await db.flush()
        if auto_commit:
            await db.commit()