# -*- coding:utf-8 -*-

from sqlalchemy import Column, ForeignKey, Integer, DateTime, String, Numeric
from config.database import BaseMixin, Base
from sqlalchemy.orm import relationship

class CarDriver(Base, BaseMixin):
    """
    司机信息表
    """
    __tablename__ = "car_driver"

    age = Column(Integer, nullable=False, comment='年龄')
    car_type = Column(Integer, nullable=False, comment='车辆类型')
    driver_years = Column(Integer, nullable=False, comment='驾龄')
    image = Column(String(255), comment='图片')
    location = Column(String(255), comment='所在位置')
    name = Column(String(255), nullable=False, comment='司机名称')
    price = Column(Numeric, nullable=False, comment='价格')
    car_info_list = relationship('CarInfo', back_populates='car_driver')


class CarInfo(Base, BaseMixin):
    """
    司机信息表
    """
    __tablename__ = 'car_info'
    name = Column(String(255), nullable=False, comment='车辆名称')
    age = Column(Integer, nullable=False, comment='车龄')
    image = Column(String(255), nullable=False, comment='图片')
    car_type = Column(Integer, nullable=False, comment='车辆类型')
    car_color = Column(String(255), nullable=False, comment='车辆颜色')
    car_driver_id = Column(Integer, ForeignKey('car_driver.id'), nullable=False, comment='车辆司机')

    car_driver = relationship('CarDriver', back_populates='car_info_list')
