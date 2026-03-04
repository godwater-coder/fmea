# -*- coding:utf-8 -*-

from sqlalchemy import Column, ForeignKey, Text, Integer, DateTime, String
from config.database import BaseMixin, Base


class SysForm(Base, BaseMixin):
    __tablename__ = "sys_form"

    content = Column(Text, nullable=False, comment='表单代码')

    form_conf = Column(Text, nullable=False, comment='表单配置')

    form_data = Column(Text, nullable=False, comment='表单内容')

    generate_conf = Column(Text, nullable=False, comment='生成配置')

    name = Column(String(255), nullable=False, comment='表单名称')

    drawing_list = Column(Text, nullable=False, comment='字段列表')

