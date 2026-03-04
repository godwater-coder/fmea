# -*- coding:utf-8 -*-
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel
from typing import List, Literal, Optional, Union
from module_admin.annotation.pydantic_annotation import as_query


class CarDriverBaseModel(BaseModel):
    """
    表对应pydantic模型
    """
    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True)
    age: Optional[int] =  Field(default=None, description='年龄')
    car_type: Optional[int] =  Field(default=None, description='车辆类型')
    create_by: Optional[int] =  Field(default=None, description='创建者')
    create_time: Optional[datetime] =  Field(default=None, description='创建时间')
    del_flag: Optional[str] =  Field(default=None, description='删除标志')
    dept_id: Optional[int] =  Field(default=None, description='部门id')
    driver_years: Optional[int] =  Field(default=None, description='驾龄')
    id: Optional[int] =  Field(default=None, description='id')
    image: Optional[str] =  Field(default=None, description='图片')
    location: Optional[str] =  Field(default=None, description='所在位置')
    name: Optional[str] =  Field(default=None, description='司机名称')
    price: Optional[float] =  Field(default=None, description='价格')
    update_time: Optional[datetime] =  Field(default=None, description='更新时间')


class CarDriverModel(CarDriverBaseModel):
    car_info_list: Optional[List['CarInfoModel']] = Field(default=None, description='子表列信息')

@as_query
class CarDriverPageModel(CarDriverBaseModel):
    """
    分页查询模型
    """
    page_num: int = Field(default=1, description='当前页码')
    page_size: int = Field(default=10, description='每页记录数')


class CarInfoModel(BaseModel):
    """
    车辆信息表对应pydantic模型
    """

    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True)

    id: Optional[int] = Field(default=None, description='id')
    create_time: Optional[datetime] = Field(default=None, description='创建时间')
    update_time: Optional[datetime] = Field(default=None, description='更新时间')
    del_flag: Optional[str] = Field(default=None, description='删除标志')
    create_by: Optional[int] = Field(default=None, description='创建者')
    dept_id: Optional[int] = Field(default=None, description='部门id')
    name: Optional[str] = Field(default=None, description='车辆名称')
    age: Optional[int] = Field(default=None, description='车龄')
    image: Optional[str] = Field(default=None, description='图片')
    car_type: Optional[int] = Field(default=None, description='车辆类型')
    car_color: Optional[str] = Field(default=None, description='车辆颜色')
    car_driver_id: Optional[int] = Field(default=None, description='车辆司机')


