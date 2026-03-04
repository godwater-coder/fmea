# -*- coding:utf-8 -*-

from typing import List
from datetime import datetime, time
from module_admin.entity.do.role_do import SysRoleDept
from sqlalchemy import and_, delete, desc, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from module_gen.constants.gen_constants import GenConstants
from sqlalchemy.orm import selectinload
from module_admin.entity.do.car_driver_do import CarDriver
from module_admin.entity.vo.car_driver_vo import CarDriverPageModel, CarDriverModel
from utils.page_util import PageUtil, PageResponseModel
from utils.common_util import CamelCaseUtil


class CarDriverDao:

    @classmethod
    async def get_by_id(cls, db: AsyncSession, car_driver_id: int) -> CarDriver:
        """根据主键获取单条记录"""
        car_driver = (((await db.execute(
                            select(CarDriver)
                            .where(CarDriver.id == car_driver_id)))
                       .scalars())
                       .first())
        return car_driver

    """
    查询
    """
    @classmethod
    async def get_car_driver_list(cls, db: AsyncSession,
                             query_object: CarDriverPageModel,
                             data_scope_sql: str = None,
                             is_page: bool = False) -> [list | PageResponseModel]:

        query = (
            select(CarDriver)
            .options(selectinload(CarDriver.car_info_list))
            .where(
                CarDriver.age == query_object.age if query_object.age else True,
                CarDriver.car_type == query_object.car_type if query_object.car_type else True,
                CarDriver.driver_years == query_object.driver_years if query_object.driver_years else True,
                CarDriver.image == query_object.image if query_object.image else True,
                CarDriver.location == query_object.location if query_object.location else True,
                CarDriver.name == query_object.name if query_object.name else True,
                CarDriver.price == query_object.price if query_object.price else True,
                CarDriver.del_flag == '0',
                eval(data_scope_sql) if data_scope_sql else True,
            )
            .order_by(desc(CarDriver.create_time))
            .distinct()
        )
        car_driver_list = await PageUtil.paginate(db, query, query_object.page_num, query_object.page_size, is_page)
        return car_driver_list


    @classmethod
    async def add_car_driver(cls, db: AsyncSession, add_model: CarDriverModel, auto_commit: bool = True) -> CarDriverModel:
        """
        增加
        """
        car_driver =  CarDriver(**add_model.model_dump(exclude_unset=True, exclude={'car_info_list',}))
        db.add(car_driver)
        await db.flush()
        car_driver_model = CarDriverModel(**CamelCaseUtil.transform_result(car_driver))
        if auto_commit:
            await db.commit()
        return car_driver_model

    @classmethod
    async def edit_car_driver(cls, db: AsyncSession, edit_model: CarDriverModel, auto_commit: bool = True) -> CarDriver:
        """
        修改
        """
        edit_dict_data = edit_model.model_dump(exclude_unset=True, exclude={ 'car_info_list', *GenConstants.DAO_COLUMN_NOT_EDIT })
        await db.execute(update(CarDriver), [edit_dict_data])
        await db.flush()
        if auto_commit:
            await db.commit()
        return await cls.get_by_id(db, edit_model.id)

    @classmethod
    async def del_car_driver(cls, db: AsyncSession, car_driver_ids: List[str], soft_del: bool = True, auto_commit: bool = True):
        """
        删除
        """
        if soft_del:
            await db.execute(update(CarDriver).where(CarDriver.id.in_(car_driver_ids)).values(del_flag='2'))
        else:
            await db.execute(delete(CarDriver).where(CarDriver.id.in_(car_driver_ids)))
        await db.flush()
        if auto_commit:
            await db.commit()