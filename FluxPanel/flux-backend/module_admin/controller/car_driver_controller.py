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

from module_admin.entity.vo.car_driver_vo import CarDriverPageModel, CarDriverModel
from module_admin.service.car_driver_service import CarDriverService

carDriverController = APIRouter(prefix='/car/driver', dependencies=[Depends(LoginService.get_current_user)])


@carDriverController.get('/list', dependencies=[Depends(CheckUserInterfaceAuth('car:driver:list'))])
async def get_car_driver_list(
        request: Request,
        query_db: AsyncSession = Depends(get_db),
        page_query: CarDriverPageModel = Depends( CarDriverPageModel.as_query),
        data_scope_sql: str = Depends(GetDataScope('CarDriver'))
):
    car_driver_result = await CarDriverService.get_car_driver_list(query_db, page_query, data_scope_sql)

    return ResponseUtil.success(model_content=car_driver_result)

@carDriverController.get('/getById/{carDriverId}', dependencies=[Depends(CheckUserInterfaceAuth('car:driver:list'))])
async def get_car_driver_by_id(
        request: Request,
        carDriverId: int,
        query_db: AsyncSession = Depends(get_db),
        data_scope_sql: str = Depends(GetDataScope('CarDriver'))
):
    car_driver = await CarDriverService.get_car_driver_by_id(query_db, carDriverId)
    return ResponseUtil.success(data=car_driver)


@carDriverController.post('/add', dependencies=[Depends(CheckUserInterfaceAuth('car:driver:add'))])
@Log(title='car_driver', business_type=BusinessType.INSERT)
async def add_car_driver (
    request: Request,
    add_model: CarDriverModel,
    query_db: AsyncSession = Depends(get_db),
    current_user: CurrentUserModel = Depends(LoginService.get_current_user),
):

    add_model.create_by = current_user.user.user_id
    add_model.dept_id = current_user.user.dept_id
    add_dict_type_result = await CarDriverService.add_car_driver(query_db, add_model)
    return ResponseUtil.success(data=add_dict_type_result)

@carDriverController.put('/update', dependencies=[Depends(CheckUserInterfaceAuth('car:driver:edit'))])
@Log(title='car_driver', business_type=BusinessType.UPDATE)
async def update_car_driver(
    request: Request,
    edit_model: CarDriverModel,
    query_db: AsyncSession = Depends(get_db),
    current_user: CurrentUserModel = Depends(LoginService.get_current_user),
):
    add_dict_type_result = await CarDriverService.update_car_driver(query_db, edit_model)
    return ResponseUtil.success(data=add_dict_type_result)


@carDriverController.delete('/delete/{carDriverIds}', dependencies=[Depends(CheckUserInterfaceAuth('car:driver:del'))])
@Log(title='car_driver', business_type=BusinessType.DELETE)
async def del_car_driver(
    request: Request,
    carDriverIds: str,
    query_db: AsyncSession = Depends(get_db),
    current_user: CurrentUserModel = Depends(LoginService.get_current_user),
):
    ids = carDriverIds.split(',')
    del_result = await CarDriverService.del_car_driver(query_db, ids)
    return ResponseUtil.success(data=del_result)

@carDriverController.post('/export', dependencies=[Depends(CheckUserInterfaceAuth('car:driver:export'))])
@Log(title='car_driver', business_type=BusinessType.EXPORT)
async def export_car_driver(
    request: Request,
    car_driver_form: CarDriverPageModel = Form(),
    query_db: AsyncSession = Depends(get_db),
    data_scope_sql: str = Depends(GetDataScope('CarDriver')),
):
    # 获取全量数据
    export_result = await CarDriverService.export_car_driver_list(
        query_db, car_driver_form, data_scope_sql
    )
    return ResponseUtil.streaming(data=bytes2file_response(export_result))

@carDriverController.post('/import', dependencies=[Depends(CheckUserInterfaceAuth('car:driver:import'))])
async def import_car_driver(request: Request,
                      import_model: ImportModel,
                      query_db: AsyncSession = Depends(get_db),
                      current_user: CurrentUserModel = Depends(LoginService.get_current_user)
    ):
    """
    导入数据
    """
    await ImportService.import_data(query_db, import_model, current_user)
    return ResponseUtil.success()