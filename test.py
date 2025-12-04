# test_connections.py
import os
import sys
from dotenv import load_dotenv
import openai
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import urllib3

# 禁用SSL警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def load_and_verify_env():
    """加载并验证环境变量"""
    print("=" * 60)
    print("🔍 环境变量加载测试")
    print("=" * 60)
    
    # 获取当前目录的绝对路径
    current_dir = os.path.dirname(os.path.abspath(__file__))
    env_file_path = os.path.join(current_dir, '.env')
    
    print(f"📁 当前目录: {current_dir}")
    print(f"📄 .env文件路径: {env_file_path}")
    
    # 检查.env文件是否存在
    if os.path.exists(env_file_path):
        print("✅ .env文件存在")
        
        # 读取.env文件内容（不加载，只查看）
        with open(env_file_path, 'r') as f:
            env_content = f.read()
        print(f"📝 .env文件内容:\n{env_content}")
        
        # 加载环境变量
        load_dotenv(env_file_path)
        print("✅ 环境变量已加载")
    else:
        print("❌ .env文件不存在")
        return False
    
    # 验证必需的环境变量
    required_vars = {
        'OPENAI_API_KEY': 'OpenAI API密钥',
        'NEO4J_URL': 'Neo4j数据库URL',
        'NEO4J_USERNAME': 'Neo4j用户名', 
        'NEO4J_PASSWORD': 'Neo4j密码'
    }
    
    print("\n🔑 环境变量验证:")
    all_present = True
    
    for var_name, description in required_vars.items():
        value = os.getenv(var_name)
        if value:
            # 对敏感信息进行脱敏显示
            if 'KEY' in var_name or 'PASSWORD' in var_name:
                display_value = f"{value[:8]}...{value[-4:]}" if len(value) > 12 else "***"
            else:
                display_value = value
            print(f"  ✅ {var_name} ({description}): {display_value}")
        else:
            print(f"  ❌ {var_name} ({description}): 未设置")
            all_present = False
    
    return all_present

def setup_openai_connection():
    """设置OpenAI连接"""
    print("\n" + "=" * 60)
    print("🤖 OpenAI连接测试")
    print("=" * 60)
    
    try:
        # 配置OpenAI
        openai.api_key = os.getenv("OPENAI_API_KEY")
        
        if not openai.api_key:
            print("❌ OpenAI API密钥未设置")
            return False
        
        # 配置自定义会话解决SSL问题
        session = requests.Session()
        session.verify = False
        
        # 配置重试策略
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        openai.requestssession = session
        print("✅ OpenAI会话配置完成")
        
        # 测试连接 - 获取模型列表
        print("🔄 正在连接OpenAI API...")
        models = openai.Model.list()
        model_count = len(models['data'])
        print(f"✅ OpenAI连接成功！")
        print(f"   📊 可用模型数量: {model_count}")
        print(f"   🔧 最近模型: {models['data'][0]['id'] if model_count > 0 else '无'}")
        
        # 测试嵌入功能
        print("🔄 测试嵌入功能...")
        embedding_response = openai.Embedding.create(
            input=["测试连接"],
            model="text-embedding-ada-002"
        )
        embedding = embedding_response['data'][0]['embedding']
        print(f"✅ 嵌入功能正常！")
        print(f"   📐 向量维度: {len(embedding)}")
        
        return True
        
    except openai.error.AuthenticationError as e:
        print(f"❌ OpenAI认证失败: {e}")
        return False
    except openai.error.APIConnectionError as e:
        print(f"❌ OpenAI连接错误: {e}")
        return False
    except Exception as e:
        print(f"❌ OpenAI测试失败: {e}")
        return False

def test_neo4j_connection():
    """测试Neo4j连接"""
    print("\n" + "=" * 60)
    print("🗃️  Neo4j连接测试")
    print("=" * 60)
    
    try:
        from neo4j import GraphDatabase
        import neo4j.exceptions
        
        neo4j_url = os.getenv("NEO4J_URL")
        username = os.getenv("NEO4J_USERNAME")
        password = os.getenv("NEO4J_PASSWORD")
        
        if not all([neo4j_url, username, password]):
            print("❌ Neo4j连接参数不完整")
            return False
        
        print(f"🔗 连接URL: {neo4j_url}")
        print(f"👤 用户名: {username}")
        print("🔐 密码: ***")
        
        # 创建驱动
        driver = GraphDatabase.driver(neo4j_url, auth=(username, password))
        
        # 测试连接
        print("🔄 正在连接Neo4j数据库...")
        with driver.session() as session:
            # 执行简单查询测试连接
            result = session.run("RETURN '连接成功' as test, timestamp() as time")
            record = result.single()
            
            if record:
                print("✅ Neo4j连接成功！")
                print(f"   ✅ 测试查询结果: {record['test']}")
                print(f"   ⏰ 服务器时间: {record['time']}")
            
            # 获取数据库信息
            db_info = session.run("CALL db.info() YIELD name, edition, version")
            db_record = db_info.single()
            if db_record:
                print(f"   🗃️  数据库: {db_record['name']}")
                print(f"   🔧 版本: {db_record['version']} ({db_record['edition']})")
        
        driver.close()
        return True
        
    except neo4j.exceptions.AuthError as e:
        print(f"❌ Neo4j认证失败: {e}")
        return False
    except neo4j.exceptions.ServiceUnavailable as e:
        print(f"❌ Neo4j服务不可用: {e}")
        return False
    except ImportError as e:
        print(f"❌ neo4j包未安装: {e}")
        print("💡 请运行: pip install neo4j")
        return False
    except Exception as e:
        print(f"❌ Neo4j连接失败: {e}")
        return False

def test_langchain_integration():
    """测试LangChain集成"""
    print("\n" + "=" * 60)
    print("🔗 LangChain集成测试")
    print("=" * 60)
    
    try:
        from langchain.embeddings.openai import OpenAIEmbeddings
        from langchain.vectorstores import Neo4jVector
        from langchain.graphs import Neo4jGraph
        
        print("🔄 初始化OpenAI嵌入...")
        embeddings = OpenAIEmbeddings(openai_api_key=os.getenv("OPENAI_API_KEY"))
        
        # 测试嵌入
        test_text = "LangChain集成测试"
        vector = embeddings.embed_query(test_text)
        print(f"✅ OpenAI嵌入初始化成功")
        print(f"   📐 向量维度: {len(vector)}")
        
        print("🔄 初始化Neo4j图数据库...")
        graph = Neo4jGraph(
            url=os.getenv("NEO4J_URL"),
            username=os.getenv("NEO4J_USERNAME"),
            password=os.getenv("NEO4J_PASSWORD")
        )
        print("✅ Neo4j图数据库连接成功")
        
        # 测试图查询
        try:
            result = graph.query("MATCH (n) RETURN count(n) as node_count LIMIT 1")
            if result and len(result) > 0:
                node_count = result[0]['node_count']
                print(f"   📊 图中节点数量: {node_count}")
        except Exception as e:
            print(f"   ⚠️  图查询测试失败: {e}")
        
        print("✅ LangChain集成测试通过")
        return True
        
    except ImportError as e:
        print(f"❌ LangChain导入失败: {e}")
        return False
    except Exception as e:
        print(f"❌ LangChain集成测试失败: {e}")
        return False

def main():
    """主测试函数"""
    print("🚀 开始连接测试...")
    
    # 测试环境变量加载
    if not load_and_verify_env():
        print("\n❌ 环境变量加载失败，测试终止")
        return
    
    # 测试OpenAI连接
    openai_success = setup_openai_connection()
    
    # 测试Neo4j连接
    neo4j_success = test_neo4j_connection()
    
    # 测试LangChain集成
    langchain_success = test_langchain_integration()
    
    # 总结结果
    print("\n" + "=" * 60)
    print("📊 测试结果总结")
    print("=" * 60)
    
    results = {
        "环境变量": True,  # 如果执行到这里，环境变量已经加载成功
        "OpenAI API": openai_success,
        "Neo4j数据库": neo4j_success,
        "LangChain集成": langchain_success
    }
    
    all_success = all(results.values())
    
    for test_name, success in results.items():
        status = "✅ 通过" if success else "❌ 失败"
        print(f"   {test_name}: {status}")
    
    if all_success:
        print("\n🎉 所有测试通过！您的环境配置正确。")
    else:
        print("\n⚠️  部分测试失败，请检查上述错误信息。")
    
    return all_success

if __name__ == "__main__":
    # 确保在正确的目录中运行
    if not os.path.exists('.env'):
        print("⚠️  请在包含.env文件的目录中运行此脚本")
        print("💡 当前目录:", os.getcwd())
    
    success = main()
    sys.exit(0 if success else 1)