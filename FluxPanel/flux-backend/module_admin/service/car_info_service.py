# -*- coding:utf-8 -*-

from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from utils.common_util import CamelCaseUtil, export_list2excel
from module_admin.entity.vo.sys_table_vo import SysTablePageModel
from module_admin.service.sys_table_service import SysTableService
from utils.page_util import PageResponseModel
from module_admin.dao.car_info_dao import CarInfoDao
from module_admin.entity.do.car_info_do import CarInfo
from module_admin.entity.vo.car_info_vo import CarInfoPageModel, CarInfoModel


class CarInfoService:
    """
    用户管理模块服务层
    """

    @classmethod
    async def get_car_info_list(cls, query_db: AsyncSession, query_object: CarInfoPageModel, data_scope_sql: str) -> [list | PageResponseModel]:
        car_info_list = await CarInfoDao.get_car_info_list(query_db, query_object, data_scope_sql, is_page=True)
        return car_info_list

    @classmethod
    async def get_car_info_by_id(cls, query_db: AsyncSession, car_info_id: int) -> CarInfoModel:
        car_info = await  CarInfoDao.get_by_id(query_db, car_info_id)
        car_info_model = CarInfoModel(**CamelCaseUtil.transform_result(car_info))
        return car_info_model


    @classmethod
    async def add_car_info(cls, query_db: AsyncSession, query_object: CarInfoModel) -> CarInfoModel:
        car_info_model = await CarInfoDao.add_car_info(query_db, query_object)
        return car_info_model


    @classmethod
    async def update_car_info(cls, query_db: AsyncSession, query_object: CarInfoModel) -> CarInfoModel:
        car_info = await CarInfoDao.edit_car_info(query_db, query_object)
        car_info_model = CarInfoModel(**CamelCaseUtil.transform_result(car_info))
        return car_info_model


    @classmethod
    async def del_car_info(cls, query_db: AsyncSession, car_info_ids: List[str]):
        await CarInfoDao.del_car_info(query_db, car_info_ids)


    @classmethod
    async def export_car_info_list(cls, query_db: AsyncSession, query_object: CarInfoPageModel, data_scope_sql) -> bytes:
        car_info_list = await CarInfoDao.get_car_info_list(query_db, query_object, data_scope_sql, is_page=False)
        filed_list = await SysTableService.get_sys_table_list(query_db, SysTablePageModel(tableName='car_info'), is_page=False)
        filtered_filed = sorted(filter(lambda x: x["show"] == '1', filed_list), key=lambda x: x["sequence"])
        new_data = []
        for item in car_info_list:
            mapping_dict = {}
            for fild in filtered_filed:
                if fild["prop"] in item:
                    mapping_dict[fild["label"]] = item[fild["prop"]]
            new_data.append(mapping_dict)
        binary_data = export_list2excel(new_data)
        return binary_data