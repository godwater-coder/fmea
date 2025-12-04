#!/bin/bash
echo "=== 极简代理测试 ==="

# 常见的主机IP地址列表
IPS="192.168.1.1 192.168.0.1 192.168.122.1 192.168.1.100 192.168.1.101"

for ip in $IPS; do
    echo -n "测试 $ip:7890 ... "
    if timeout 3 curl -s -I --proxy http://$ip:7890 https://httpbin.org/ip &>/dev/null; then
        echo "✅ 成功！"
        echo "使用命令: export HTTP_PROXY=http://$ip:7890"
        exit 0
    else
        echo "❌ 失败"
    fi
done

echo "所有IP测试失败，请检查Clash配置"
