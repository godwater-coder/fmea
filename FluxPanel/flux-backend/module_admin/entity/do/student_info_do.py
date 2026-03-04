# -*- coding:utf-8 -*-

from sqlalchemy import Column, ForeignKey, String, Integer, DateTime
from config.database import BaseMixin, Base


class StudentInfo(Base, BaseMixin):
    __tablename__ = "student_info"

    class_name = Column(String(50), comment='班级')

    date_of_birth = Column(DateTime, comment='出生日期')

    email = Column(String(100), comment='电子邮箱')

    gender = Column(String(1), nullable=False, comment='性别')

    major = Column(String(100), comment='专业')

    name = Column(String(50), nullable=False, comment='姓名')

    phone_number = Column(String(20), comment='联系电话')

