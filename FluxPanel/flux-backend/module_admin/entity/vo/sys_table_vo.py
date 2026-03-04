# -*- coding:utf-8 -*-
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel
from typing import List, Literal, Optional, Union
from module_admin.annotation.pydantic_annotation import as_query


class SysTableModel(BaseModel):
    """
    表对应pydantic模型
    """
    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True)
    align: Optional[str] =  Field(default=None, description='对其方式')
    create_time: Optional[datetime] =  Field(default=None, description='创建时间')
    del_flag: Optional[str] =  Field(default=None, description='删除标志')
    field_name: Optional[str] =  Field(default=None, description='字段名')
    fixed: Optional[str] =  Field(default=None, description='固定表头')
    id: Optional[int] =  Field(default=None, description='ID')
    label: Optional[str] =  Field(default=None, description='字段标签')
    label_tip: Optional[str] =  Field(default=None, description='字段标签解释')
    prop: Optional[str] =  Field(default=None, description='驼峰属性')
    show: Optional[str] =  Field(default=None, description='可见')
    sortable: Optional[str] =  Field(default=None, description='可排序')
    table_name: Optional[str] =  Field(default=None, description='表名')
    tooltip: Optional[str] =  Field(default=None, description='超出隐藏')
    update_by: Optional[int] =  Field(default=None, description='更新者')
    update_by_name: Optional[str] =  Field(default=None, description='更新者')
    update_time: Optional[datetime] =  Field(default=None, description='更新时间')
    width: Optional[int] =  Field(default=None, description='宽度')
    sequence: Optional[int] =  Field(default=None, description='字段顺序')

@as_query
class SysTablePageModel(SysTableModel):
    """
    分页查询模型
    """
    page_num: int = Field(default=1, description='当前页码')
    page_size: int = Field(default=10, description='每页记录数')


@as_query
class DbTablePageModel(BaseModel):
    """
    分页查询模型
    """
    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True)
    table_name: Optional[str] = Field(default=None, description='表名')
    table_comment: Optional[str] = Field(default=None, description='表描述')
    page_num: int = Field(default=1, description='当前页码')
    page_size: int = Field(default=10, description='每页记录数')

class SysTableColumnIdsModel(BaseModel):
    """
    列排序
    """
    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True)
    ids: Optional[List[int]] = Field()