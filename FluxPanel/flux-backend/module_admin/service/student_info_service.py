# -*- coding:utf-8 -*-

from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from utils.common_util import CamelCaseUtil, export_list2excel
from module_admin.entity.vo.sys_table_vo import SysTablePageModel
from module_admin.service.sys_table_service import SysTableService
from utils.page_util import PageResponseModel
from module_admin.dao.student_info_dao import StudentInfoDao
from module_admin.entity.do.student_info_do import StudentInfo
from module_admin.entity.vo.student_info_vo import StudentInfoPageModel, StudentInfoModel


class StudentInfoService:
    """
    用户管理模块服务层
    """

    @classmethod
    async def get_student_info_list(cls, query_db: AsyncSession, query_object: StudentInfoPageModel, data_scope_sql: str) -> [list | PageResponseModel]:
        student_info_list = await StudentInfoDao.get_student_info_list(query_db, query_object, data_scope_sql, is_page=True)
        return student_info_list

    @classmethod
    async def get_student_info_by_id(cls, query_db: AsyncSession, student_info_id: int) -> StudentInfoModel:
        student_info = await  StudentInfoDao.get_by_id(query_db, student_info_id)
        student_info_model = StudentInfoModel(**CamelCaseUtil.transform_result(student_info))
        return student_info_model


    @classmethod
    async def add_student_info(cls, query_db: AsyncSession, query_object: StudentInfoModel) -> StudentInfoModel:
        student_info = await StudentInfoDao.add_student_info(query_db, query_object)
        student_info_model = StudentInfoModel(**CamelCaseUtil.transform_result(student_info))
        return student_info_model


    @classmethod
    async def update_student_info(cls, query_db: AsyncSession, query_object: StudentInfoModel) -> StudentInfoModel:
        student_info = await StudentInfoDao.edit_student_info(query_db, query_object)
        student_info_model = StudentInfoModel(**CamelCaseUtil.transform_result(student_info))
        return student_info_model


    @classmethod
    async def del_student_info(cls, query_db: AsyncSession, student_info_ids: List[str]):
        await StudentInfoDao.del_student_info(query_db, student_info_ids)


    @classmethod
    async def export_student_info_list(cls, query_db: AsyncSession, query_object: StudentInfoPageModel, data_scope_sql) -> bytes:
        student_info_list = await StudentInfoDao.get_student_info_list(query_db, query_object, data_scope_sql, is_page=False)
        filed_list = await SysTableService.get_sys_table_list(query_db, SysTablePageModel(tableName='student_info'), is_page=False)
        filtered_filed = sorted(filter(lambda x: x["show"] == '1', filed_list), key=lambda x: x["sequence"])
        new_data = []
        for item in student_info_list:
            mapping_dict = {}
            for fild in filtered_filed:
                if fild["prop"] in item:
                    mapping_dict[fild["label"]] = item[fild["prop"]]
            new_data.append(mapping_dict)
        binary_data = export_list2excel(new_data)
        return binary_data