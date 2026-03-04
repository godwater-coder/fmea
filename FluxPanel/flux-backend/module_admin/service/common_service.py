import os
import time
from datetime import datetime
from pathlib import Path

import oss2
from Crypto.SelfTest.Cipher.test_OFB import file_name
from fastapi import BackgroundTasks, Request, UploadFile
from config.env import UploadConfig, OSSConfig
from exceptions.exception import ServiceException
from module_admin.entity.vo.common_vo import CrudResponseModel, UploadResponseModel
from utils.upload_util import UploadUtil


class CommonService:
    """
    通用模块服务层
    """

    @classmethod
    async def upload_local(cls, file: UploadFile):
        """
        通用上传service

        :param request: Request对象
        :param file: 上传文件对象
        :return: 上传结果
        """
        if not UploadUtil.check_file_extension(file):
            raise ServiceException(message='文件类型不合法')
        else:
            relative_path = f'upload/{datetime.now().strftime("%Y")}/{datetime.now().strftime("%m")}/{datetime.now().strftime("%d")}'
            dir_path = os.path.join(UploadConfig.UPLOAD_PATH, relative_path)
            try:
                os.makedirs(dir_path)
            except FileExistsError:
                pass
            filename = f'{file.filename.rsplit(".", 1)[0]}_{datetime.now().strftime("%Y%m%d%H%M%S")}{UploadConfig.UPLOAD_MACHINE}{UploadUtil.generate_random_number()}.{file.filename.rsplit(".")[-1]}'
            filepath = os.path.join(dir_path, filename)
            with open(filepath, 'wb') as f:
                # 流式写出大型文件，这里的10代表10MB
                for chunk in iter(lambda: file.file.read(1024 * 1024 * 10), b''):
                    f.write(chunk)

            return CrudResponseModel(
                is_success=True,
                result=UploadResponseModel(
                    fileName=filepath,
                    newFileName=filename,
                    originalFilename=file.filename,
                    url=f'{UploadConfig.UPLOAD_PREFIX}/{relative_path}/{filename}',
                ),
                message='上传成功',
            )

    @classmethod
    async def upload_oss(cls, file: UploadFile, oss_folder):
        end_point = OSSConfig.ALI_OSS_END_POINT
        access_key_id = OSSConfig.ALI_OSS_KEY
        access_key_secret = OSSConfig.ALI_OSS_SECRET
        access_pre = OSSConfig.ALI_OSS_PRE
        auth = oss2.Auth(access_key_id, access_key_secret)
        bucket = oss2.Bucket(auth, end_point, OSSConfig.ALI_OSS_BUCKET)
        pic_data = file.file.read()
        # file_name = oss_folder + str(time.time()) + file.filename.rsplit(".", 1)[-1]
        target_file_name = oss_folder + str(time.time()) + Path(file.filename).suffix
        bucket.put_object(target_file_name, pic_data)

        return CrudResponseModel(
            is_success=True,
            result=UploadResponseModel(
                file_name= file.filename,
                new_file_name=target_file_name,
                original_filename=file.filename,
                url=f'{access_pre}/{target_file_name}',
            ),
            message='上传成功',
        )


    @classmethod
    async def download_services(cls, background_tasks: BackgroundTasks, file_name, delete: bool):
        """
        下载下载目录文件service

        :param background_tasks: 后台任务对象
        :param file_name: 下载的文件名称
        :param delete: 是否在下载完成后删除文件
        :return: 上传结果
        """
        filepath = os.path.join(UploadConfig.DOWNLOAD_PATH, file_name)
        if '..' in file_name:
            raise ServiceException(message='文件名称不合法')
        elif not UploadUtil.check_file_exists(filepath):
            raise ServiceException(message='文件不存在')
        else:
            if delete:
                background_tasks.add_task(UploadUtil.delete_file, filepath)
            return CrudResponseModel(is_success=True, result=UploadUtil.generate_file(filepath), message='下载成功')

    @classmethod
    async def download_resource_services(cls, resource: str):
        """
        下载上传目录文件service

        :param resource: 下载的文件名称
        :return: 上传结果
        """
        filepath = os.path.join(resource.replace(UploadConfig.UPLOAD_PREFIX, UploadConfig.UPLOAD_PATH))
        filename = resource.rsplit('/', 1)[-1]
        if (
            '..' in filename
            or not UploadUtil.check_file_timestamp(filename)
            or not UploadUtil.check_file_machine(filename)
            or not UploadUtil.check_file_random_code(filename)
        ):
            raise ServiceException(message='文件名称不合法')
        elif not UploadUtil.check_file_exists(filepath):
            raise ServiceException(message='文件不存在')
        else:
            return CrudResponseModel(is_success=True, result=UploadUtil.generate_file(filepath), message='下载成功')
