# -*- coding:utf-8 -*-

from sqlalchemy import Column, ForeignKey, Integer, DateTime, String, Text
from config.database import BaseMixin, Base
from module_admin.entity.do.sys_form_do import SysForm


class SysFormData(Base, BaseMixin):
    __tablename__ = "sys_form_data"

    form_data = Column(Text, nullable=False, comment='表单数据')

    form_id = Column(Integer, ForeignKey(SysForm.id), nullable=False, comment='表单ID')

    form_name = Column(String(255), nullable=False, comment='表单名称')

