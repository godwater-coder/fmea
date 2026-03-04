# -*- coding:utf-8 -*-

from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from utils.common_util import CamelCaseUtil, export_list2excel
from module_admin.entity.vo.sys_table_vo import SysTablePageModel
from module_admin.service.sys_table_service import SysTableService
from utils.page_util import PageResponseModel
from module_admin.dao.car_driver_dao import CarDriverDao
from module_admin.entity.do.car_driver_do import CarDriver
from module_admin.entity.vo.car_driver_vo import CarDriverPageModel, CarDriverModel


class CarDriverService:
    """
    用户管理模块服务层
    """

    @classmethod
    async def get_car_driver_list(cls, query_db: AsyncSession, query_object: CarDriverPageModel, data_scope_sql: str) -> [list | PageResponseModel]:
        car_driver_list = await CarDriverDao.get_car_driver_list(query_db, query_object, data_scope_sql, is_page=True)
        return car_driver_list

    @classmethod
    async def get_car_driver_by_id(cls, query_db: AsyncSession, car_driver_id: int) -> CarDriverModel:
        car_driver = await  CarDriverDao.get_by_id(query_db, car_driver_id)
        car_driver_model = CarDriverModel(**CamelCaseUtil.transform_result(car_driver))
        return car_driver_model


    @classmethod
    async def add_car_driver(cls, query_db: AsyncSession, query_object: CarDriverModel) -> CarDriverModel:
        car_driver_model = await CarDriverDao.add_car_driver(query_db, query_object)
        return car_driver_model


    @classmethod
    async def update_car_driver(cls, query_db: AsyncSession, query_object: CarDriverModel) -> CarDriverModel:
        car_driver = await CarDriverDao.edit_car_driver(query_db, query_object)
        car_driver_model = CarDriverModel(**CamelCaseUtil.transform_result(car_driver))
        return car_driver_model


    @classmethod
    async def del_car_driver(cls, query_db: AsyncSession, car_driver_ids: List[str]):
        await CarDriverDao.del_car_driver(query_db, car_driver_ids)


    @classmethod
    async def export_car_driver_list(cls, query_db: AsyncSession, query_object: CarDriverPageModel, data_scope_sql) -> bytes:
        car_driver_list = await CarDriverDao.get_car_driver_list(query_db, query_object, data_scope_sql, is_page=False)
        filed_list = await SysTableService.get_sys_table_list(query_db, SysTablePageModel(tableName='car_driver'), is_page=False)
        filtered_filed = sorted(filter(lambda x: x["show"] == '1', filed_list), key=lambda x: x["sequence"])
        new_data = []
        for item in car_driver_list:
            mapping_dict = {}
            for fild in filtered_filed:
                if fild["prop"] in item:
                    mapping_dict[fild["label"]] = item[fild["prop"]]
            new_data.append(mapping_dict)
        binary_data = export_list2excel(new_data)
        return binary_data