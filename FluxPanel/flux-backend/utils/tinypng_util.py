import os
import shutil

import tinify
tinify.key = "MmX1s99N5jvdWny8xB8VqD6LYLpBDGjL"


def get_image_paths(directory):
    # 图片文件扩展名
    image_extensions = ('.jpg', '.jpeg', '.png', '.bmp', '.webp')

    # 存储图片路径的列表
    image_paths = []
    # 遍历目录
    for filename in os.listdir(directory):
        # 获取文件的完整路径
        filepath = os.path.join(directory, filename)
        # 检查文件是否为图片（根据扩展名）
        if os.path.isfile(filepath) and filename.lower().endswith(image_extensions):
            image_paths.append(filepath)
    return image_paths


def start_compress(folder: str):
    file_list = get_image_paths(folder)
    compressed_folder = folder + 'compressed'
    if not os.path.exists(compressed_folder):
        os.makedirs(compressed_folder)
        print("创建文件夹" + compressed_folder)
    for i, file in enumerate(file_list):
        source = tinify.from_file(file)
        target_file = os.path.join(compressed_folder, file.split('/')[-1])
        source.to_file(target_file)
        print("压缩成功==" + target_file)


start_compress('../static/templates/unzip')