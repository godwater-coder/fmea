# -*- coding:utf-8 -*-
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel
from typing import List, Literal, Optional, Union
from module_admin.annotation.pydantic_annotation import as_query


class StudentInfoModel(BaseModel):
    """
    表对应pydantic模型
    """
    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True)
    class_name: Optional[str] =  Field(default=None, description='班级')
    create_by: Optional[int] =  Field(default=None, description='创建者')
    create_time: Optional[datetime] =  Field(default=None, description='创建时间')
    date_of_birth: Optional[datetime] =  Field(default=None, description='出生日期')
    del_flag: Optional[str] =  Field(default=None, description='删除标志')
    dept_id: Optional[int] =  Field(default=None, description='部门id')
    email: Optional[str] =  Field(default=None, description='电子邮箱')
    gender: Optional[str] =  Field(default=None, description='性别')
    id: Optional[int] =  Field(default=None, description='ID')
    major: Optional[str] =  Field(default=None, description='专业')
    name: Optional[str] =  Field(default=None, description='姓名')
    phone_number: Optional[str] =  Field(default=None, description='联系电话')
    update_time: Optional[datetime] =  Field(default=None, description='更新时间')


@as_query
class StudentInfoPageModel(StudentInfoModel):
    """
    分页查询模型
    """
    page_num: int = Field(default=1, description='当前页码')
    page_size: int = Field(default=10, description='每页记录数')