# -*- coding:utf-8 -*-

from typing import List
from datetime import datetime, time
from module_admin.entity.do.role_do import SysRoleDept
from sqlalchemy import and_, delete, desc, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from module_gen.constants.gen_constants import GenConstants
from module_admin.entity.do.car_info_do import CarInfo
from module_admin.entity.vo.car_info_vo import CarInfoPageModel, CarInfoModel
from utils.page_util import PageUtil, PageResponseModel
from utils.common_util import CamelCaseUtil


class CarInfoDao:

    @classmethod
    async def get_by_id(cls, db: AsyncSession, car_info_id: int) -> CarInfo:
        """根据主键获取单条记录"""
        car_info = (((await db.execute(
                            select(CarInfo)
                            .where(CarInfo.id == car_info_id)))
                       .scalars())
                       .first())
        return car_info

    """
    查询
    """
    @classmethod
    async def get_car_info_list(cls, db: AsyncSession,
                             query_object: CarInfoPageModel,
                             data_scope_sql: str = None,
                             is_page: bool = False) -> [list | PageResponseModel]:

        query = (
            select(CarInfo)
            .where(
                CarInfo.age == query_object.age if query_object.age else True,
                CarInfo.car_color == query_object.car_color if query_object.car_color else True,
                CarInfo.car_type == query_object.car_type if query_object.car_type else True,
                CarInfo.image == query_object.image if query_object.image else True,
                CarInfo.name == query_object.name if query_object.name else True,
                CarInfo.del_flag == '0',
                eval(data_scope_sql) if data_scope_sql else True,
            )
            .order_by(desc(CarInfo.create_time))
            .distinct()
        )
        car_info_list = await PageUtil.paginate(db, query, query_object.page_num, query_object.page_size, is_page)
        return car_info_list


    @classmethod
    async def add_car_info(cls, db: AsyncSession, add_model: CarInfoModel, auto_commit: bool = True) -> CarInfoModel:
        """
        增加
        """
        car_info =  CarInfo(**add_model.model_dump(exclude_unset=True, ))
        db.add(car_info)
        await db.flush()
        car_info_model = CarInfoModel(**CamelCaseUtil.transform_result(car_info))
        if auto_commit:
            await db.commit()
        return car_info_model

    @classmethod
    async def edit_car_info(cls, db: AsyncSession, edit_model: CarInfoModel, auto_commit: bool = True) -> CarInfo:
        """
        修改
        """
        edit_dict_data = edit_model.model_dump(exclude_unset=True, exclude={ *GenConstants.DAO_COLUMN_NOT_EDIT })
        await db.execute(update(CarInfo), [edit_dict_data])
        await db.flush()
        if auto_commit:
            await db.commit()
        return await cls.get_by_id(db, edit_model.car_driver_id)

    @classmethod
    async def del_car_info(cls, db: AsyncSession, car_info_ids: List[str], soft_del: bool = True, auto_commit: bool = True):
        """
        删除
        """
        if soft_del:
            await db.execute(update(CarInfo).where(CarInfo.id.in_(car_info_ids)).values(del_flag='2'))
        else:
            await db.execute(delete(CarInfo).where(CarInfo.id.in_(car_info_ids)))
        await db.flush()
        if auto_commit:
            await db.commit()