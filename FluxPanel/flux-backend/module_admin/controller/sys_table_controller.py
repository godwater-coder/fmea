# -*- coding:utf-8 -*-

from fastapi import APIRouter, Depends, Form, Query
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
from module_gen.entity.vo.gen_table_vo import GenTablePageModel
from utils.response_util import ResponseUtil
from utils.common_util import bytes2file_response

from module_admin.entity.vo.sys_table_vo import SysTablePageModel, SysTableModel, DbTablePageModel, \
    SysTableColumnIdsModel
from module_admin.service.sys_table_service import SysTableService

sysTableController = APIRouter(prefix='/sys/table', dependencies=[Depends(LoginService.get_current_user)])


@sysTableController.get('/list', dependencies=[Depends(CheckUserInterfaceAuth('sys:table:list'))])
async def get_sys_table_list(
        request: Request,
        query_db: AsyncSession = Depends(get_db),
        page_query: SysTablePageModel = Depends( SysTablePageModel.as_query),
        data_scope_sql: str = Depends(GetDataScope('SysDept'))
):
    sys_table_result = await SysTableService.get_sys_table_list(query_db, page_query, data_scope_sql)

    return ResponseUtil.success(model_content=sys_table_result)

@sysTableController.get('/listAll')
async def get_sys_table_list(
        request: Request,
        query_db: AsyncSession = Depends(get_db),
        page_query: SysTablePageModel = Depends( SysTablePageModel.as_query)
):
    sys_table_result = await SysTableService.get_sys_table_list(query_db, page_query, is_page=False)
    return ResponseUtil.success(data=sys_table_result)

@sysTableController.get('/db/list', dependencies=[Depends(CheckUserInterfaceAuth('tool:gen:list'))])
async def gen_db_list(request: Request,
            gen_table: DbTablePageModel = Depends(DbTablePageModel.as_query),
            query_db: AsyncSession = Depends(get_db),
            data_scope_sql: str = Depends(GetDataScope('SysDept'))):
    """查询数据库列表"""
    db_list = await SysTableService.select_db_table_list(gen_table, query_db, data_scope_sql)
    return ResponseUtil.success(model_content=db_list)

@sysTableController.get('/getById/{sysTableId}', dependencies=[Depends(CheckUserInterfaceAuth('sys:table:list'))])
async def get_sys_table_by_id(
        request: Request,
        sysTableId: int,
        query_db: AsyncSession = Depends(get_db),
        data_scope_sql: str = Depends(GetDataScope('SysDept'))
):
    sys_table = await SysTableService.get_sys_table_by_id(query_db, sysTableId)
    return ResponseUtil.success(data=sys_table)


@sysTableController.post('/add', dependencies=[Depends(CheckUserInterfaceAuth('sys:table:add'))])
@Log(title='sys_table', business_type=BusinessType.INSERT)
async def add_sys_table (
    request: Request,
    add_model: SysTableModel,
    query_db: AsyncSession = Depends(get_db),
    current_user: CurrentUserModel = Depends(LoginService.get_current_user),
):
    add_dict_type_result = await SysTableService.add_sys_table(query_db, add_model)
    return ResponseUtil.success(data=add_dict_type_result)

@sysTableController.post('/import', dependencies=[Depends(CheckUserInterfaceAuth('sys:table:add'))])
@Log(title='sys_table', business_type=BusinessType.INSERT)
async def import_sys_table (
    request: Request,
    tables: str = Query(None),
    query_db: AsyncSession = Depends(get_db),
    current_user: CurrentUserModel = Depends(LoginService.get_current_user),
):
    tables_array = tables.split(',') if tables else []
    operate_log = "导入表" + ",".join(tables_array)
    await SysTableService.import_sys_table(query_db, tables_array)
    return ResponseUtil.success(msg=operate_log)

@sysTableController.put('/update', dependencies=[Depends(CheckUserInterfaceAuth('sys:table:update'))])
@Log(title='sys_table', business_type=BusinessType.UPDATE)
async def update_sys_table(
    request: Request,
    edit_model: SysTableModel,
    query_db: AsyncSession = Depends(get_db),
    current_user: CurrentUserModel = Depends(LoginService.get_current_user),
):
    add_dict_type_result = await SysTableService.update_sys_table(query_db, edit_model)
    return ResponseUtil.success(data=add_dict_type_result)


@sysTableController.delete('/delete/{sysTableIds}', dependencies=[Depends(CheckUserInterfaceAuth('sys:table:del'))])
@Log(title='sys_table', business_type=BusinessType.DELETE)
async def del_sys_table(
    request: Request,
    sysTableIds: str,
    query_db: AsyncSession = Depends(get_db),
    current_user: CurrentUserModel = Depends(LoginService.get_current_user),
):
    ids = sysTableIds.split(',')
    del_result = await SysTableService.del_sys_table(query_db, ids)
    return ResponseUtil.success(data=del_result)

@sysTableController.post('/export', dependencies=[Depends(CheckUserInterfaceAuth('sys:table:export'))])
@Log(title='sys_table', business_type=BusinessType.EXPORT)
async def export_sys_table(
    request: Request,
    sys_table_form: SysTablePageModel = Form(),
    query_db: AsyncSession = Depends(get_db),
    data_scope_sql: str = Depends(GetDataScope('SysDept')),
):
    # 获取全量数据
    export_result = await SysTableService.export_sys_table_list(
        query_db, sys_table_form, data_scope_sql
    )
    return ResponseUtil.streaming(data=bytes2file_response(export_result))

@sysTableController.post('/column/sort', dependencies=[Depends(CheckUserInterfaceAuth('sys:table:update'))])
@Log(title='sys_table', business_type=BusinessType.UPDATE)
async def sys_table_column_sort (
    request: Request,
    ids_model: SysTableColumnIdsModel,
    query_db: AsyncSession = Depends(get_db)
):
    await SysTableService.sort_column(query_db, ids_model.ids)
    return ResponseUtil.success()