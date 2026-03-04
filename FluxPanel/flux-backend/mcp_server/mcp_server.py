
from typing import Literal

from mcp.server.fastmcp import FastMCP

from tool_table import TableTool
from tool_weather import WeatherTool

# 初始化 MCP 服务器
mcp = FastMCP("FluxMcpServer")


@mcp.tool()
async def query_weather(city: str) -> str:
    """
    输入指定城市的英文名称，返回今日天气查询结果。
    :param city: 城市名称（需使用英文）
    :return: 格式化后的天气信息
    """
    data = await WeatherTool.fetch_weather(city)
    return WeatherTool.format_weather(data)

@mcp.tool()
async def query_table(table_name: Literal["car_driver", "student_info"]) -> str:
    """
    输入指定表名，获取表内的数据。
     Args:
        table_name: 表名选项:
            - car_driver: 司机信息
            - student_info: 学生信息表
    return: 数据表内容
    """
    data = await TableTool.fetch_table_data(table_name)
    return data


if __name__ == "__main__":
    # 以标准 I/O 方式运行 MCP 服务器
    mcp.run(transport='stdio')