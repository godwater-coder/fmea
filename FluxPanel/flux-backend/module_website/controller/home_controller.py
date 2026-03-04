# -*- coding:utf-8 -*-
"""
@Time : 2022/4/23 8:33 PM
@Author: binkuolo
@Des: views home
"""
import json

from fastapi import Request, APIRouter, Depends, Form
from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader
from oss2.exceptions import status
from starlette.templating import Jinja2Templates

from config.get_db import get_db
from module_website.utils import format_date
from utils.response_util import ResponseUtil
from utils.time_format_util import list_format_datetime, format_datetime_dict_list

homeRouter = APIRouter()

templates = Jinja2Templates(directory="static/templates")
templates.env.filters['format_date'] = format_date


@homeRouter.get("/", response_class=HTMLResponse)
async def home_page(request: Request):
    """
    门户首页
    :param request:
    :return:
    """
    # return request.app.state.views.TemplateResponse("index.html", {"request": request})
    # return render_template('index.html', title=title, content=content)

    page_name = "index"
    async for query_db in get_db():
        return templates.TemplateResponse(
            'index.html',  # 第一个参数放模板文件
            {
                'request': request,  # 注意，返回模板响应时，必须有request键值对，且值为Request请求对象
                'current_path': str(request.url.path),
            },
        )
    return ResponseUtil.error()
