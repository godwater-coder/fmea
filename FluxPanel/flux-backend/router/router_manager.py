from fastapi import APIRouter

from module_admin.controller.cache_controller import cacheController
from module_admin.controller.captcha_controller import captchaController
from module_admin.controller.car_driver_controller import carDriverController
from module_admin.controller.common_controller import commonController
from module_admin.controller.config_controller import configController
from module_admin.controller.dept_controller import deptController
from module_admin.controller.dict_controller import dictController
from module_admin.controller.import_controller import importController
from module_admin.controller.log_controller import logController
from module_admin.controller.login_controller import loginController
from module_admin.controller.job_controller import jobController
from module_admin.controller.menu_controller import menuController
from module_admin.controller.notice_controller import noticeController
from module_admin.controller.online_controller import onlineController
from module_admin.controller.post_controler import postController
from module_admin.controller.role_controller import roleController
from module_admin.controller.server_controller import serverController
from module_admin.controller.student_info_controller import studentInfoController
from module_admin.controller.sys_form_controller import sysFormController
from module_admin.controller.sys_form_data_controller import sysFormDataController
from module_admin.controller.sys_table_controller import sysTableController
from module_admin.controller.user_controller import userController
from module_app.controller.app_login_controller import appLoginController
from module_gen.controller.gen_controller import gen1Controller
from module_website.controller.home_controller import homeRouter

admin_controllers = [
    {'router': loginController, 'tags': ['登录模块']},
    {'router': captchaController, 'tags': ['验证码模块']},
    {'router': userController, 'tags': ['系统管理-用户管理']},
    {'router': roleController, 'tags': ['系统管理-角色管理']},
    {'router': menuController, 'tags': ['系统管理-菜单管理']},
    {'router': sysTableController, 'tags': ['系统管理-表格管理']},
    {'router': deptController, 'tags': ['系统管理-部门管理']},
    {'router': postController, 'tags': ['系统管理-岗位管理']},
    {'router': dictController, 'tags': ['系统管理-字典管理']},
    {'router': configController, 'tags': ['系统管理-参数管理']},
    {'router': noticeController, 'tags': ['系统管理-通知公告管理']},
    {'router': logController, 'tags': ['系统管理-日志管理']},
    {'router': onlineController, 'tags': ['系统监控-在线用户']},
    {'router': jobController, 'tags': ['系统监控-定时任务']},
    {'router': serverController, 'tags': ['系统监控-菜单管理']},
    {'router': cacheController, 'tags': ['系统监控-缓存监控']},
    {'router': commonController, 'tags': ['通用模块']},
    {'router': gen1Controller, 'tags': ['系统工具-代码生成']},
    {'router': sysFormController, 'tags': ['系统工具-表单构建']},
    {'router': sysFormDataController, 'tags': ['系统工具-表单构建']},
    {'router': homeRouter, 'tags': ['产品官网']},
    {'router': carDriverController, 'tags': ['测试业务']},
    {'router': studentInfoController, 'tags': ['测试业务']},
    {'router': importController, 'tags': ['导入数据']}



]

app_controllers = [
    {'router': appLoginController, 'prefix': '/wechat', 'tags': ['登录模块']},
]

def get_admin_router():
    admin_router = APIRouter(prefix="")
    for controller in admin_controllers:
        admin_router.include_router(router=controller.get('router'), tags=controller.get('tags'))
    return admin_router

def get_app_router():
    app_router = APIRouter(prefix="/api/v1")
    for controller in app_controllers:
        app_router.include_router(router=controller.get('router'), prefix=controller.get('prefix') ,
                                  tags=controller.get('tags'))
    return app_router


def register_router():
    all_router = APIRouter()
    all_router.include_router(router=get_admin_router())
    all_router.include_router(router=get_app_router())
    return all_router

