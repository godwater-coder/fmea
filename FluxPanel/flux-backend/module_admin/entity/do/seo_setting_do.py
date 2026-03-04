# -*- coding:utf-8 -*-

from sqlalchemy import Column, ForeignKey, DateTime, Integer, String
from config.database import BaseMixin, Base


class SeoSetting(Base, BaseMixin):
    __tablename__ = "seo_setting"
    
    
    
    page_name = Column(String(length=255), comment='页面名称')
    
    keywords = Column(String(length=500), comment='页面关键词')
    
    title = Column(String(length=500), comment='页面title标题')
    
    description = Column(String(length=3000), comment='页面描述')
    
    
    
    
    
    
    
