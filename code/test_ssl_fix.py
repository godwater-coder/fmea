# -*- coding: utf-8 -*-
"""
OpenAI SSL连接修复测试脚本 - 增强版
位置：kg-rag-fmea/code/test_ssl_fix.py
"""

import os
import sys
import openai
import requests
import urllib3
import ssl
import socket
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from urllib3.poolmanager import PoolManager

# 添加项目根目录到Python路径，确保可以导入其他模块
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

class SSLContextAdapter(HTTPAdapter):
    """自定义SSL上下文适配器"""
    def __init__(self, ssl_context=None, **kwargs):
        self.ssl_context = ssl_context
        super().__init__(**kwargs)
    
    def init_poolmanager(self, connections, maxsize, block=False, **pool_kwargs):
        self.poolmanager = PoolManager(
            num_pools=connections,
            maxsize=maxsize,
            block=block,
            ssl_context=self.ssl_context,
            **pool_kwargs
        )

def create_ssl_context():
    """创建自定义SSL上下文，彻底禁用验证"""
    context = ssl.create_default_context()
    
    # 彻底禁用SSL验证
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    
    # 设置较低的SSL安全级别
    try:
        context.set_ciphers('DEFAULT@SECLEVEL=1')
    except:
        pass  # 某些系统可能不支持
    
    # 允许较旧的协议版本
    context.options |= ssl.OP_NO_SSLv2
    context.options |= ssl.OP_NO_SSLv3
    # 不限制TLS版本，让系统自动协商
    
    return context

def setup_ssl_fix_aggressive():
    """更激进的SSL验证禁用方案"""
    print("=== 设置激进的SSL验证禁用 ===")
    
    # 彻底禁用SSL警告
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    # 设置环境变量
    os.environ['CURL_CA_BUNDLE'] = ''
    os.environ['REQUESTS_CA_BUNDLE'] = ''
    os.environ['SSL_CERT_FILE'] = ''
    
    # 加载环境变量（从项目根目录的.env文件）
    env_path = os.path.join(project_root, '.env')
    load_dotenv(env_path)
    print(f"✅ 已加载环境变量从: {env_path}")
    
    # 创建自定义SSL上下文
    ssl_context = create_ssl_context()
    
    # 创建会话并应用自定义SSL上下文
    session = requests.Session()
    
    # 使用自定义适配器
    adapter = SSLContextAdapter(ssl_context=ssl_context, max_retries=3)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    
    # 彻底禁用验证
    session.verify = False
    session.trust_env = False  # 不信任系统代理设置
    
    # 应用到OpenAI
    openai.requestssession = session
    openai.api_key = os.getenv("OPENAI_API_KEY")
    
    # 设置较长的超时时间
    openai.api_requestor.API_REQUEST_TIMEOUT = 60
    
    print("✅ 激进的SSL验证禁用配置完成")
    print(f"✅ Session verify: {session.verify}")
    print(f"✅ Session trust_env: {session.trust_env}")
    
    return True

def test_network_connectivity():
    """测试网络连通性"""
    print("\n=== 网络连通性测试 ===")
    
    # 测试DNS解析
    try:
        ip = socket.gethostbyname('api.openai.com')
        print(f"✅ DNS解析成功: api.openai.com -> {ip}")
    except Exception as e:
        print(f"❌ DNS解析失败: {e}")
        return False
    
    # 测试端口连通性
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)
        result = sock.connect_ex(('api.openai.com', 443))
        sock.close()
        if result == 0:
            print("✅ 端口443连通性正常")
        else:
            print(f"❌ 端口443无法连接: 错误码 {result}")
            return False
    except Exception as e:
        print(f"❌ 端口检查失败: {e}")
        return False
    
    # 测试HTTP连接
    try:
        response = requests.get('https://api.openai.com', timeout=10, verify=False)
        print(f"✅ 直接HTTP请求成功: 状态码 {response.status_code}")
        return True
    except Exception as e:
        print(f"❌ 直接HTTP请求失败: {e}")
        return False

def test_openai_connection_aggressive():
    """使用更激进的方法测试OpenAI连接"""
    print("\n=== 激进方法测试OpenAI连接 ===")
    
    # 方法1: 直接使用requests调用API
    api_key = os.getenv("OPENAI_API_KEY")
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }
    
    try:
        # 使用与OpenAI库相同的URL
        response = requests.get(
            'https://api.openai.com/v1/models',
            headers=headers,
            timeout=30,
            verify=False
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ 直接API调用成功！模型数量: {len(data['data'])}")
            return True
        else:
            print(f"❌ API调用失败: 状态码 {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ 直接API调用失败: {e}")
    
    # 方法2: 尝试使用urllib3直接调用
    try:
        import urllib3
        http = urllib3.PoolManager(cert_reqs='CERT_NONE')
        response = http.request(
            'GET',
            'https://api.openai.com/v1/models',
            headers=headers,
            timeout=urllib3.Timeout(total=30)
        )
        if response.status == 200:
            print("✅ urllib3调用成功！")
            return True
        else:
            print(f"❌ urllib3调用失败: 状态码 {response.status}")
            return False
    except Exception as e:
        print(f"❌ urllib3调用失败: {e}")
    
    return False

def test_openai_with_proxy():
    """使用代理测试OpenAI连接"""
    print("\n=== 代理连接测试 ===")
    
    # 常见代理地址
    proxies_list = [
        {'http': 'http://127.0.0.1:7890', 'https': 'http://127.0.0.1:7890'},
        {'http': 'http://127.0.0.1:1080', 'https': 'http://127.0.0.1:1080'},
        {'http': 'http://127.0.0.1:8080', 'https': 'http://127.0.0.1:8080'},
        {'http': 'http://localhost:7890', 'https': 'http://localhost:7890'},
    ]
    
    api_key = os.getenv("OPENAI_API_KEY")
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }
    
    for proxy in proxies_list:
        try:
            print(f"尝试代理: {proxy['https']}")
            
            response = requests.get(
                'https://api.openai.com/v1/models',
                headers=headers,
                proxies=proxy,
                timeout=15,
                verify=False
            )
            
            if response.status_code == 200:
                print(f"✅ 代理 {proxy['https']} 连接成功！")
                return True
                
        except Exception as e:
            print(f"❌ 代理 {proxy['https']} 失败: {e}")
            continue
    
    print("❌ 所有代理配置都失败")
    return False

def test_neo4j_connection():
    """测试Neo4j连接"""
    print("\n=== 测试Neo4j连接 ===")
    
    try:
        from neo4j import GraphDatabase
        
        driver = GraphDatabase.driver(
            os.getenv("NEO4J_URL"),
            auth=(os.getenv("NEO4J_USERNAME"), os.getenv("NEO4J_PASSWORD"))
        )
        
        with driver.session() as session:
            result = session.run("RETURN '连接成功' as test, timestamp() as time")
            record = result.single()
            print(f"✅ Neo4j连接成功！")
            print(f"   测试结果: {record['test']}")
        
        driver.close()
        return True
    except Exception as e:
        print(f"❌ Neo4j连接失败: {e}")
        return False

def main():
    """主函数"""
    print("🚀 开始SSL修复测试 - 增强版...")
    
    # 测试网络连通性
    network_ok = test_network_connectivity()
    
    # 设置SSL修复
    setup_ssl_fix_aggressive()
    
    # 测试连接
    openai_success = test_openai_connection_aggressive()
    
    # 如果直接连接失败，尝试代理
    if not openai_success:
        print("\n⚠️ 直接连接失败，尝试代理...")
        openai_success = test_openai_with_proxy()
    
    neo4j_success = test_neo4j_connection()
    
    # 输出结果
    print("\n" + "="*60)
    print("📊 测试结果总结")
    print("="*60)
    print(f"网络连通性: {'✅ 成功' if network_ok else '❌ 失败'}")
    print(f"OpenAI连接: {'✅ 成功' if openai_success else '❌ 失败'}")
    print(f"Neo4j连接: {'✅ 成功' if neo4j_success else '❌ 失败'}")
    
    if all([openai_success, neo4j_success]):
        print("\n🎉 所有测试通过！可以运行主程序了。")
    else:
        print("\n⚠️ 部分测试失败，需要进一步排查。")
        
        if not openai_success:
            print("\n💡 OpenAI连接失败建议:")
            print("1. 检查网络环境是否限制OpenAI访问")
            print("2. 尝试使用VPN或代理服务器")
            print("3. 联系网络管理员解决企业网络限制")
            print("4. 考虑使用其他AI服务提供商")

if __name__ == "__main__":
    main()