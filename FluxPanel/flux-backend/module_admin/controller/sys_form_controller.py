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

from module_admin.entity.vo.sys_form_vo import SysFormPageModel, SysFormModel
from module_admin.service.sys_form_service import SysFormService

sysFormController = APIRouter(prefix='/sys/form', dependencies=[Depends(LoginService.get_current_user)])


@sysFormController.get('/list', dependencies=[Depends(CheckUserInterfaceAuth('sys:form:list'))])
async def get_sys_form_list(
        request: Request,
        query_db: AsyncSession = Depends(get_db),
        page_query: SysFormPageModel = Depends( SysFormPageModel.as_query),
        data_scope_sql: str = Depends(GetDataScope('SysForm'))
):
    sys_form_result = await SysFormService.get_sys_form_list(query_db, page_query, data_scope_sql)

    return ResponseUtil.success(model_content=sys_form_result)

@sysFormController.get('/getById/{sysFormId}', dependencies=[Depends(CheckUserInterfaceAuth('sys:form:list'))])
async def get_sys_form_by_id(
        request: Request,
        sysFormId: int,
        query_db: AsyncSession = Depends(get_db),
        data_scope_sql: str = Depends(GetDataScope('SysForm'))
):
    sys_form = await SysFormService.get_sys_form_by_id(query_db, sysFormId)
    return ResponseUtil.success(data=sys_form)


@sysFormController.post('/add', dependencies=[Depends(CheckUserInterfaceAuth('sys:form:add'))])
@Log(title='sys_form', business_type=BusinessType.INSERT)
async def add_sys_form (
    request: Request,
    add_model: SysFormModel,
    query_db: AsyncSession = Depends(get_db),
    current_user: CurrentUserModel = Depends(LoginService.get_current_user),
):

    add_model.create_by = current_user.user.user_id
    add_model.dept_id = current_user.user.dept_id
    add_dict_type_result = await SysFormService.add_sys_form(query_db, add_model)
    return ResponseUtil.success(data=add_dict_type_result)

@sysFormController.put('/update', dependencies=[Depends(CheckUserInterfaceAuth('sys:form:edit'))])
@Log(title='sys_form', business_type=BusinessType.UPDATE)
async def update_sys_form(
    request: Request,
    edit_model: SysFormModel,
    query_db: AsyncSession = Depends(get_db),
    current_user: CurrentUserModel = Depends(LoginService.get_current_user),
):
    add_dict_type_result = await SysFormService.update_sys_form(query_db, edit_model)
    return ResponseUtil.success(data=add_dict_type_result)


@sysFormController.delete('/delete/{sysFormIds}', dependencies=[Depends(CheckUserInterfaceAuth('sys:form:del'))])
@Log(title='sys_form', business_type=BusinessType.DELETE)
async def del_sys_form(
    request: Request,
    sysFormIds: str,
    query_db: AsyncSession = Depends(get_db),
    current_user: CurrentUserModel = Depends(LoginService.get_current_user),
):
    ids = sysFormIds.split(',')
    del_result = await SysFormService.del_sys_form(query_db, ids)
    return ResponseUtil.success(data=del_result)

@sysFormController.post('/export', dependencies=[Depends(CheckUserInterfaceAuth('sys:form:export'))])
@Log(title='sys_form', business_type=BusinessType.EXPORT)
async def export_sys_form(
    request: Request,
    sys_form_form: SysFormPageModel = Form(),
    query_db: AsyncSession = Depends(get_db),
    data_scope_sql: str = Depends(GetDataScope('SysForm')),
):
    # 获取全量数据
    export_result = await SysFormService.export_sys_form_list(
        query_db, sys_form_form, data_scope_sql
    )
    return ResponseUtil.streaming(data=bytes2file_response(export_result))