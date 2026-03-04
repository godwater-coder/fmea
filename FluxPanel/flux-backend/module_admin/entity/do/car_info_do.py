# -*- coding:utf-8 -*-

from sqlalchemy import Column, ForeignKey, Integer, String, DateTime
from config.database import BaseMixin, Base

class CarInfo(Base, BaseMixin):
    """
    车辆信息表
    """
    __tablename__ = "car_info"

    age = Column(Integer, nullable=False, comment='车龄')
    car_color = Column(String(255), comment='车辆颜色')
    car_driver_id = Column(Integer, primary_key=True, comment='车辆司机')
    car_type = Column(Integer, nullable=False, comment='车辆类型')
    image = Column(String(255), comment='图片')
    name = Column(String(255), nullable=False, comment='车辆名称')


