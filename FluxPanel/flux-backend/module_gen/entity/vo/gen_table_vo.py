# -*- coding:utf-8 -*-
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel
from typing import List, Literal, Optional, Union, Dict, Any, Set
from module_admin.annotation.pydantic_annotation import as_query
from module_gen.constants.gen_constants import GenConstants
from module_gen.entity.vo.gen_table_column_vo import GenTableColumnModel


class GenTableBaseModel(BaseModel):
    """
    表对应pydantic模型
    """
    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True)
    
    table_id: Optional[int] =  Field(default=None, description='编号')
    
    table_name: Optional[str] =  Field(default=None, description='表名称')
    
    table_comment: Optional[str] =  Field(default=None, description='表描述')
    
    sub_table_name: Optional[str] =  Field(default=None, description='关联子表的表名')
    
    sub_table_fk_name: Optional[str] =  Field(default=None, description='子表关联的外键名')
    
    class_name: Optional[str] =  Field(default=None, description='实体类名称')
    
    tpl_category: Optional[str] =  Field(default=None, description='使用的模板（crud单表操作 tree树表操作）')
    
    tpl_web_type: Optional[str] =  Field(default=None, description='前端模板类型（element-ui模版 element-plus模版）')
    
    package_name: Optional[str] =  Field(default=None, description='生成包路径')
    
    module_name: Optional[str] =  Field(default=None, description='生成模块名')
    
    business_name: Optional[str] =  Field(default=None, description='生成业务名')
    
    function_name: Optional[str] =  Field(default=None, description='生成功能名')
    
    function_author: Optional[str] =  Field(default=None, description='生成功能作者')
    
    gen_type: Optional[str] =  Field(default=None, description='生成代码方式（0zip压缩包 1自定义路径）')
    
    gen_path: Optional[str] =  Field(default=None, description='生成路径（不填默认项目路径）')
    
    options: Optional[str] =  Field(default=None, description='其它生成选项')
    
    create_by: Optional[str] =  Field(default=None, description='创建者')
    
    create_time: Optional[datetime] =  Field(default=None, description='创建时间')
    
    update_by: Optional[str] =  Field(default=None, description='更新者')
    
    update_time: Optional[datetime] =  Field(default=None, description='更新时间')
    
    remark: Optional[str] =  Field(default=None, description='备注')

    params: Optional[Any] = Field(default=None, description='前端传递过来的表附加信息，转换成json字符串后放到options')




class GenTableModel(GenTableBaseModel):
    """
    代码生成业务表模型
    """

    pk_column: Optional['GenTableColumnModel'] = Field(default=None, description='主键信息')
    sub_table: Optional['GenTableModel'] = Field(default=None, description='子表信息')
    columns: Optional[List['GenTableColumnModel']] = Field(default=None, description='表列信息')
    tree_code: Optional[str] = Field(default=None, description='树编码字段')
    tree_parent_code: Optional[str] = Field(default=None, description='树父编码字段')
    tree_name: Optional[str] = Field(default=None, description='树名称字段')
    parent_menu_id: Optional[int] = Field(default=None, description='解析出options里面的parentMenuId给前端用')
    parent_menu_name: Optional[str] = Field(default=None, description='上级菜单名称字段')
    sub: Optional[bool] = Field(default=None, description='是否为子表')
    tree: Optional[bool] = Field(default=None, description='是否为树表')
    crud: Optional[bool] = Field(default=None, description='是否为单表')

    @model_validator(mode='after')
    def check_some_is(self) -> 'GenTableModel':
        self.sub = True if self.tpl_category and self.tpl_category == GenConstants.TPL_SUB else False
        self.tree = True if self.tpl_category and self.tpl_category == GenConstants.TPL_TREE else False
        self.crud = True if self.tpl_category and self.tpl_category == GenConstants.TPL_CRUD else False
        return self

@as_query
class GenTablePageModel(GenTableBaseModel):
    """
    分页查询模型
    """
    page_num: int = Field(default=1, description='当前页码')
    page_size: int = Field(default=10, description='每页记录数')

@as_query
class GenTableIdsModel(BaseModel):
    """表的table_ids, 逗号分隔"""
    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True)
    tb_ids: Optional[str] = Field(description='当前页码')
