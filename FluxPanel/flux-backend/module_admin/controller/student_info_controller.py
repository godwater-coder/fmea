# -*- coding:utf-8 -*-

from fastapi import APIRouter, Depends, Form
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request
from typing import List
from config.enums import BusinessType
from config.get_db import get_db
from module_admin.entity.vo.import_vo import ImportModel
from module_admin.service.import_service import ImportService
from module_admin.service.login_service import LoginService
from module_admin.aspect.data_scope import GetDataScope
from module_admin.aspect.interface_auth import CheckUserInterfaceAuth
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_admin.annotation.log_annotation import Log
from utils.response_util import ResponseUtil
from utils.common_util import bytes2file_response

from module_admin.entity.vo.student_info_vo import StudentInfoPageModel, StudentInfoModel
from module_admin.service.student_info_service import StudentInfoService

studentInfoController = APIRouter(prefix='/student/info', dependencies=[Depends(LoginService.get_current_user)])


@studentInfoController.get('/list', dependencies=[Depends(CheckUserInterfaceAuth('student:info:list'))])
async def get_student_info_list(
        request: Request,
        query_db: AsyncSession = Depends(get_db),
        page_query: StudentInfoPageModel = Depends( StudentInfoPageModel.as_query),
        data_scope_sql: str = Depends(GetDataScope('StudentInfo'))
):
    student_info_result = await StudentInfoService.get_student_info_list(query_db, page_query, data_scope_sql)

    return ResponseUtil.success(model_content=student_info_result)

@studentInfoController.get('/getById/{studentInfoId}', dependencies=[Depends(CheckUserInterfaceAuth('student:info:list'))])
async def get_student_info_by_id(
        request: Request,
        studentInfoId: int,
        query_db: AsyncSession = Depends(get_db),
        data_scope_sql: str = Depends(GetDataScope('StudentInfo'))
):
    student_info = await StudentInfoService.get_student_info_by_id(query_db, studentInfoId)
    return ResponseUtil.success(data=student_info)


@studentInfoController.post('/add', dependencies=[Depends(CheckUserInterfaceAuth('student:info:add'))])
@Log(title='student_info', business_type=BusinessType.INSERT)
async def add_student_info (
    request: Request,
    add_model: StudentInfoModel,
    query_db: AsyncSession = Depends(get_db),
    current_user: CurrentUserModel = Depends(LoginService.get_current_user),
):

    add_model.create_by = current_user.user.user_id
    add_model.dept_id = current_user.user.dept_id
    add_dict_type_result = await StudentInfoService.add_student_info(query_db, add_model)
    return ResponseUtil.success(data=add_dict_type_result)

@studentInfoController.put('/update', dependencies=[Depends(CheckUserInterfaceAuth('student:info:edit'))])
@Log(title='student_info', business_type=BusinessType.UPDATE)
async def update_student_info(
    request: Request,
    edit_model: StudentInfoModel,
    query_db: AsyncSession = Depends(get_db),
    current_user: CurrentUserModel = Depends(LoginService.get_current_user),
):
    add_dict_type_result = await StudentInfoService.update_student_info(query_db, edit_model)
    return ResponseUtil.success(data=add_dict_type_result)


@studentInfoController.delete('/delete/{studentInfoIds}', dependencies=[Depends(CheckUserInterfaceAuth('student:info:del'))])
@Log(title='student_info', business_type=BusinessType.DELETE)
async def del_student_info(
    request: Request,
    studentInfoIds: str,
    query_db: AsyncSession = Depends(get_db),
    current_user: CurrentUserModel = Depends(LoginService.get_current_user),
):
    ids = studentInfoIds.split(',')
    del_result = await StudentInfoService.del_student_info(query_db, ids)
    return ResponseUtil.success(data=del_result)

@studentInfoController.post('/export', dependencies=[Depends(CheckUserInterfaceAuth('student:info:export'))])
@Log(title='student_info', business_type=BusinessType.EXPORT)
async def export_student_info(
    request: Request,
    student_info_form: StudentInfoPageModel = Form(),
    query_db: AsyncSession = Depends(get_db),
    data_scope_sql: str = Depends(GetDataScope('StudentInfo')),
):
    # 获取全量数据
    export_result = await StudentInfoService.export_student_info_list(
        query_db, student_info_form, data_scope_sql
    )
    return ResponseUtil.streaming(data=bytes2file_response(export_result))

@studentInfoController.post('/import', dependencies=[Depends(CheckUserInterfaceAuth('student:info:import'))])
async def import_student_info(request: Request,
                      import_model: ImportModel,
                      query_db: AsyncSession = Depends(get_db),
                      current_user: CurrentUserModel = Depends(LoginService.get_current_user)
    ):
    """
    导入数据
    """
    await ImportService.import_data(query_db, import_model, current_user)
    return ResponseUtil.success()