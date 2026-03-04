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

from module_admin.entity.vo.car_info_vo import CarInfoPageModel, CarInfoModel
from module_admin.service.car_info_service import CarInfoService

carInfoController = APIRouter(prefix='/car/info', dependencies=[Depends(LoginService.get_current_user)])


@carInfoController.get('/list', dependencies=[Depends(CheckUserInterfaceAuth('car:info:list'))])
async def get_car_info_list(
        request: Request,
        query_db: AsyncSession = Depends(get_db),
        page_query: CarInfoPageModel = Depends( CarInfoPageModel.as_query),
        data_scope_sql: str = Depends(GetDataScope('CarInfo'))
):
    car_info_result = await CarInfoService.get_car_info_list(query_db, page_query, data_scope_sql)

    return ResponseUtil.success(model_content=car_info_result)

@carInfoController.get('/getById/{carInfoId}', dependencies=[Depends(CheckUserInterfaceAuth('car:info:list'))])
async def get_car_info_by_id(
        request: Request,
        carInfoId: int,
        query_db: AsyncSession = Depends(get_db),
        data_scope_sql: str = Depends(GetDataScope('CarInfo'))
):
    car_info = await CarInfoService.get_car_info_by_id(query_db, carInfoId)
    return ResponseUtil.success(data=car_info)


@carInfoController.post('/add', dependencies=[Depends(CheckUserInterfaceAuth('car:info:add'))])
@Log(title='car_info', business_type=BusinessType.INSERT)
async def add_car_info (
    request: Request,
    add_model: CarInfoModel,
    query_db: AsyncSession = Depends(get_db),
    current_user: CurrentUserModel = Depends(LoginService.get_current_user),
):

    add_model.create_by = current_user.user.user_id
    add_model.dept_id = current_user.user.dept_id
    add_dict_type_result = await CarInfoService.add_car_info(query_db, add_model)
    return ResponseUtil.success(data=add_dict_type_result)

@carInfoController.put('/update', dependencies=[Depends(CheckUserInterfaceAuth('car:info:edit'))])
@Log(title='car_info', business_type=BusinessType.UPDATE)
async def update_car_info(
    request: Request,
    edit_model: CarInfoModel,
    query_db: AsyncSession = Depends(get_db),
    current_user: CurrentUserModel = Depends(LoginService.get_current_user),
):
    add_dict_type_result = await CarInfoService.update_car_info(query_db, edit_model)
    return ResponseUtil.success(data=add_dict_type_result)


@carInfoController.delete('/delete/{carInfoIds}', dependencies=[Depends(CheckUserInterfaceAuth('car:info:del'))])
@Log(title='car_info', business_type=BusinessType.DELETE)
async def del_car_info(
    request: Request,
    carInfoIds: str,
    query_db: AsyncSession = Depends(get_db),
    current_user: CurrentUserModel = Depends(LoginService.get_current_user),
):
    ids = carInfoIds.split(',')
    del_result = await CarInfoService.del_car_info(query_db, ids)
    return ResponseUtil.success(data=del_result)

@carInfoController.post('/export', dependencies=[Depends(CheckUserInterfaceAuth('car:info:export'))])
@Log(title='car_info', business_type=BusinessType.EXPORT)
async def export_car_info(
    request: Request,
    car_info_form: CarInfoPageModel = Form(),
    query_db: AsyncSession = Depends(get_db),
    data_scope_sql: str = Depends(GetDataScope('CarInfo')),
):
    # 获取全量数据
    export_result = await CarInfoService.export_car_info_list(
        query_db, car_info_form, data_scope_sql
    )
    return ResponseUtil.streaming(data=bytes2file_response(export_result))

@carInfoController.post('/import', dependencies=[Depends(CheckUserInterfaceAuth('car:info:import'))])
async def import_car_info(request: Request,
                      import_model: ImportModel,
                      query_db: AsyncSession = Depends(get_db),
                      current_user: CurrentUserModel = Depends(LoginService.get_current_user)
    ):
    """
    导入数据
    """
    await ImportService.import_data(query_db, import_model, current_user)
    return ResponseUtil.success()