# -*- coding:utf-8 -*-

from fastapi import APIRouter, Depends, Form
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request
from typing import List
from config.enums import BusinessType
from config.get_db import get_db
from module_admin.service.login_service import LoginService
from module_admin.aspect.data_scope import GetDataScope
from module_admin.aspect.interface_auth import CheckUserInterfaceAuth
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_admin.annotation.log_annotation import Log
from utils.response_util import ResponseUtil
from utils.common_util import bytes2file_response

from module_admin.entity.vo.sys_form_data_vo import SysFormDataPageModel, SysFormDataModel
from module_admin.service.sys_form_data_service import SysFormDataService

sysFormDataController = APIRouter(prefix='/sys/form_data')


@sysFormDataController.get('/list')
async def get_sys_form_data_list(
        request: Request,
        query_db: AsyncSession = Depends(get_db),
        page_query: SysFormDataPageModel = Depends( SysFormDataPageModel.as_query)
):
    sys_form_data_result = await SysFormDataService.get_sys_form_data_list(query_db, page_query, None)

    return ResponseUtil.success(model_content=sys_form_data_result)

@sysFormDataController.get('/getById/{sysFormDataId}', dependencies=[Depends(CheckUserInterfaceAuth('sys:form_data:list'))])
async def get_sys_form_data_by_id(
        request: Request,
        sysFormDataId: int,
        query_db: AsyncSession = Depends(get_db),
        data_scope_sql: str = Depends(GetDataScope('SysFormData'))
):
    sys_form_data = await SysFormDataService.get_sys_form_data_by_id(query_db, sysFormDataId)
    return ResponseUtil.success(data=sys_form_data)


@sysFormDataController.post('/add')
@Log(title='sys_form_data', business_type=BusinessType.INSERT)
async def add_sys_form_data (
    request: Request,
    add_model: SysFormDataModel,
    query_db: AsyncSession = Depends(get_db),
    current_user: CurrentUserModel = Depends(LoginService.get_current_user),
):

    add_model.create_by = current_user.user.user_id
    add_model.dept_id = current_user.user.dept_id
    add_dict_type_result = await SysFormDataService.add_sys_form_data(query_db, add_model)
    return ResponseUtil.success(data=add_dict_type_result)

@sysFormDataController.put('/update', dependencies=[Depends(CheckUserInterfaceAuth('sys:form_data:edit'))])
@Log(title='sys_form_data', business_type=BusinessType.UPDATE)
async def update_sys_form_data(
    request: Request,
    edit_model: SysFormDataModel,
    query_db: AsyncSession = Depends(get_db),
    current_user: CurrentUserModel = Depends(LoginService.get_current_user),
):
    add_dict_type_result = await SysFormDataService.update_sys_form_data(query_db, edit_model)
    return ResponseUtil.success(data=add_dict_type_result)


@sysFormDataController.delete('/delete/{sysFormDataIds}', dependencies=[Depends(CheckUserInterfaceAuth('sys:form_data:del'))])
@Log(title='sys_form_data', business_type=BusinessType.DELETE)
async def del_sys_form_data(
    request: Request,
    sysFormDataIds: str,
    query_db: AsyncSession = Depends(get_db),
    current_user: CurrentUserModel = Depends(LoginService.get_current_user),
):
    ids = sysFormDataIds.split(',')
    del_result = await SysFormDataService.del_sys_form_data(query_db, ids)
    return ResponseUtil.success(data=del_result)

@sysFormDataController.post('/export', dependencies=[Depends(CheckUserInterfaceAuth('sys:form_data:export'))])
@Log(title='sys_form_data', business_type=BusinessType.EXPORT)
async def export_sys_form_data(
    request: Request,
    sys_form_data_form: SysFormDataPageModel = Form(),
    query_db: AsyncSession = Depends(get_db),
    data_scope_sql: str = Depends(GetDataScope('SysFormData')),
):
    # 获取全量数据
    export_result = await SysFormDataService.export_sys_form_data_list(
        query_db, sys_form_data_form, data_scope_sql
    )
    return ResponseUtil.streaming(data=bytes2file_response(export_result))