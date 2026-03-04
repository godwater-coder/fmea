from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel
from typing import Literal, Optional


class ImportFieldModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True)
    base_column: Optional[str] = Field(description='数据库字段名')
    excel_column: Optional[str] = Field(description='excel字段名', default=None)
    default_value: Optional[str] = Field(description='默认值', default=None)
    is_required: Optional[str] = Field(description='是否必传')
    selected: Optional[bool] = Field(description='是否勾选')


class ImportModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True)
    table_name: Optional[str] = Field(description='表名')
    sheet_name: Optional[str] = Field(description='Sheet名')
    filed_info: Optional[list[ImportFieldModel]] = Field(description='字段关联表')
    file_name: Optional[str] = Field(description='文件名')

