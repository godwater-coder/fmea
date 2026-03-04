from fastapi import APIRouter, BackgroundTasks, Depends, File, Query, Request, UploadFile, Form
from sqlalchemy.ext.asyncio import AsyncSession

from config.env import OSSConfig
from config.get_db import get_db
from module_admin.service.common_service import CommonService
from module_admin.service.import_service import ImportService
from module_admin.service.login_service import LoginService
from utils.log_util import logger
from utils.response_util import ResponseUtil

importController = APIRouter(prefix='/import', dependencies=[Depends(LoginService.get_current_user)])

@importController.post('/uploadExcel')
async def upload_excel(request: Request, tableName:str = Form(), file: UploadFile = File(...),
                       query_db: AsyncSession = Depends(get_db),):
    """
    本地上传专用，用于临时解析，无需持久化存储的文件
    """

    result = await ImportService.analysis_excel(query_db, tableName, file)

    return ResponseUtil.success(data=result)

