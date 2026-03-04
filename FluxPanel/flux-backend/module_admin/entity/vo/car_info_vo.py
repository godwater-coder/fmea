# -*- coding:utf-8 -*-
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel
from typing import List, Literal, Optional, Union
from module_admin.annotation.pydantic_annotation import as_query


class CarInfoModel(BaseModel):
    """
    表对应pydantic模型
    """
    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True)
    age: Optional[int] =  Field(default=None, description='车龄')
    car_color: Optional[str] =  Field(default=None, description='车辆颜色')
    car_driver_id: Optional[int] =  Field(default=None, description='车辆司机')
    car_type: Optional[int] =  Field(default=None, description='车辆类型')
    create_by: Optional[int] =  Field(default=None, description='创建者')
    create_time: Optional[datetime] =  Field(default=None, description='创建时间')
    del_flag: Optional[str] =  Field(default=None, description='删除标志')
    dept_id: Optional[int] =  Field(default=None, description='部门id')
    id: Optional[int] =  Field(default=None, description='id')
    image: Optional[str] =  Field(default=None, description='图片')
    name: Optional[str] =  Field(default=None, description='车辆名称')
    update_time: Optional[datetime] =  Field(default=None, description='更新时间')



@as_query
class CarInfoPageModel(CarInfoModel):
    """
    分页查询模型
    """
    page_num: int = Field(default=1, description='当前页码')
    page_size: int = Field(default=10, description='每页记录数')


