import json
from datetime import datetime

import numpy as np
import pandas as pd
from fastapi import UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession

from exceptions.exception import ServiceException
from module_admin.dao.import_dao import ImportDao
from module_admin.entity.vo.import_vo import ImportModel
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_admin.service.common_service import CommonService
from module_gen.constants.gen_constants import GenConstants
from utils.common_util import CamelCaseUtil


class ImportService:
    """
    解析Excel和数据表的Columns
    """

    @classmethod
    async def analysis_excel(cls, query_db: AsyncSession, table_name: str, file: UploadFile = File(...)):
        upload_result = await CommonService.upload_local(file)
        table_columns = await ImportDao.select_table_columns_by_name(query_db, table_name)
        edit_columns = [col for col in table_columns if col.column_name not in GenConstants.COLUMN_NAME_NOT_EDIT]

        # 获取所有sheet名称
        excel_file = pd.ExcelFile(upload_result.result.file_name, engine="openpyxl")
        sheet_names = excel_file.sheet_names

        sheet_excel_columns = []
        for sheet_name in sheet_names:
            excel_columns = pd.read_excel(upload_result.result.file_name, sheet_name=sheet_name, engine="openpyxl").columns
            sheet_excel_columns.append({
                "sheet_name": sheet_name, #返回所有sheet名称供前端选择'
                "excel_columns": list(excel_columns)
            })

        result = {
            "sheet_names": sheet_names,
            "sheet_excel_columns": sheet_excel_columns,
            "table_columns": edit_columns,
            "filename": upload_result.result.file_name
        }
        return CamelCaseUtil.transform_result(result)

    @classmethod
    async def import_data(cls, query_db: AsyncSession, import_model: ImportModel, current_user: CurrentUserModel):
        field_list = [model.base_column for model in import_model.filed_info if model.selected]

        sheet_name = import_model.sheet_name if import_model.sheet_name else 0
        df = pd.read_excel(import_model.file_name, sheet_name=sheet_name, dtype=str, engine="openpyxl")
        # 替换NaN为None，防止写入数据库报错
        df.replace(np.nan, None, inplace=True)
        df_dict = df.to_dict(orient="records")
        print(df_dict)
        value_list = []
        for excel_item in df_dict:
            value_item = []
            for model in import_model.filed_info:
                if model.selected: # 已勾选的才能添加
                    if not model.excel_column and not model.default_value:
                        raise ServiceException(message='勾选的字段，必须设置列或者添加默认值')
                    if model.excel_column:
                        value_item.append(excel_item[model.excel_column])
                    else:
                        value_item.append(model.default_value)
            # 额外添加用户ID和部门ID
            value_item.extend([current_user.user.user_id, current_user.user.dept_id, datetime.now(), datetime.now()])
            value_list.append(value_item)
        field_list.extend(['create_by', 'dept_id', 'create_time', 'update_time'])
        await ImportDao.import_data(query_db, import_model.table_name, field_list, value_list)
