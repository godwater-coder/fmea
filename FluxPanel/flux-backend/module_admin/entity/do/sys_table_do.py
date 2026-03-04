# -*- coding:utf-8 -*-
import datetime

from sqlalchemy import Column, ForeignKey, String, DateTime, Integer, text
from config.database import Base


class SysTable(Base):
    __tablename__ = "sys_table"

    id = Column(Integer, primary_key=True, autoincrement=True)
    create_time = Column(DateTime, nullable=False, default=datetime.datetime.now, comment='创建时间')
    update_time = Column(DateTime, nullable=False, default=datetime.datetime.now,
                         onupdate=datetime.datetime.now, index=True, comment='更新时间')
    del_flag = Column(String(1), nullable=False, default='0', server_default=text("'0'"),
                      comment='删除标志（0代表存在 2代表删除）')


    align = Column(String(255), nullable=False, default='left', comment='对其方式')

    field_name = Column(String(255), nullable=False, comment='字段名')

    fixed = Column(String(1), nullable=False, default='0', comment='固定表头')

    label = Column(String(255), nullable=False, comment='字段标签')

    label_tip = Column(String(255), comment='字段标签解释')

    prop = Column(String(255), nullable=False, comment='驼峰属性')

    show = Column(String(1), nullable=False, default='1', comment='可见')

    sortable = Column(String(1), nullable=False, default='0', comment='可排序')

    table_name = Column(String(255), nullable=False, comment='表名')

    tooltip = Column(String(1), nullable=False, default='1', comment='超出隐藏')

    update_by = Column(Integer, comment='更新者')

    update_by_name = Column(String(255), comment='更新者')

    width = Column(Integer, nullable=False, default=150, comment='宽度')

    sequence = Column(Integer, nullable=False, default=0, comment='字段顺序')

