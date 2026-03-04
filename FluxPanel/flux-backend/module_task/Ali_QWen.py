
import os
from typing import List

# from openai import OpenAI
#
# client = OpenAI(
#     # 若没有配置环境变量，请用百炼API Key将下行替换为：api_key="sk-xxx",
#     api_key=os.getenv("QWEN_API_KEY"),
#     base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
# )

def get_article(keywords: List[str]):
    return None
    # user_words = f"帮我写一篇关于{'、'.join(keywords)}相关的文章, 八百字左右，内容尽可能的详细、也可以举一些例子"
    # with open('module_task/template/article_system.txt', 'r') as f:
    #     system_words = f.read()
    #     completion = client.chat.completions.create(
    #         model="qwen-turbo-1101", # 模型列表：https://help.aliyun.com/zh/model-studio/getting-started/models
    #         messages=[
    #             {'role': 'system', 'content': system_words},
    #             {'role': 'user', 'content': user_words}
    #         ],
    #     )
    #     return completion.model_dump_json()
