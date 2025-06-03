#!/usr/bin/env python3
"""
test_docker_network.py

Диагностика сетевых проблем внутри Docker контейнера
"""

import asyncio
import socket
import subprocess
import sys
import httpx
import dns.resolver
import time
import os


async def test_basic_connectivity():
    """Базовые тесты сетевого подключения"""
    print("🔍 Диагностика сетевого подключения Docker контейнера")
    print("=" * 60)
    
    tests = []
    
    # 1. DNS resolution test
    print("\n1️⃣ Тестирование DNS resolution...")
    try:
        result = socket.gethostbyname("google.com")
        print(f"✅ DNS работает: google.com -> {result}")
        tests.append(("DNS Resolution", True))
    except Exception as e:
        print(f"❌ DNS не работает: {e}")
        tests.append(("DNS Resolution", False))
    
    # 2. Python DNS resolution
    print("\n2️⃣ Тестирование Python DNS...")
    try:
        import dns.resolver
        answers = dns.resolver.resolve("google.com", "A")
        ip = str(answers[0])
        print(f"✅ Python DNS работает: google.com -> {ip}")
        tests.append(("Python DNS", True))
    except Exception as e:
        print(f"❌ Python DNS не работает: {e}")
        tests.append(("Python DNS", False))
    
    # 3. HTTP connectivity test
    print("\n3️⃣ Тестирование HTTP подключения...")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get("https://httpbin.org/get")
            if response.status_code == 200:
                print(f"✅ HTTP работает: статус {response.status_code}")
                tests.append(("HTTP Connectivity", True))
            else:
                print(f"⚠️ HTTP частично работает: статус {response.status_code}")
                tests.append(("HTTP Connectivity", False))
    except Exception as e:
        print(f"❌ HTTP не работает: {e}")
        tests.append(("HTTP Connectivity", False))
    
    # 4. TwitterAPI.io specific test
    print("\n4️⃣ Тестирование доступа к TwitterAPI.io...")
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            # Пробуем просто подключиться к хосту
            response = await client.get("https://api.twitterapi.io")
            print(f"✅ TwitterAPI.io доступен: статус {response.status_code}")
            tests.append(("TwitterAPI.io Access", True))
    except Exception as e:
        print(f"❌ TwitterAPI.io недоступен: {e}")
        tests.append(("TwitterAPI.io Access", False))
    
    # 5. DNS servers test
    print("\n5️⃣ Проверка DNS серверов...")
    try:
        with open("/etc/resolv.conf", "r") as f:
            resolv_content = f.read()
            print("DNS серверы в /etc/resolv.conf:")
            print(resolv_content)
            tests.append(("DNS Config", True))
    except Exception as e:
        print(f"❌ Не удается прочитать /etc/resolv.conf: {e}")
        tests.append(("DNS Config", False))
    
    # 6. Multiple domain resolution test
    print("\n6️⃣ Тестирование разрешения разных доменов...")
    domains_to_test = [
        "api.twitterapi.io",
        "api.openai.com", 
        "httpbin.org",
        "github.com"
    ]
    
    resolved_domains = 0
    for domain in domains_to_test:
        try:
            ip = socket.gethostbyname(domain)
            print(f"✅ {domain} -> {ip}")
            resolved_domains += 1
        except Exception as e:
            print(f"❌ {domain} -> ОШИБКА: {e}")
    
    domain_test_passed = resolved_domains == len(domains_to_test)
    tests.append(("Multi-Domain Resolution", domain_test_passed))
    print(f"Разрешено {resolved_domains}/{len(domains_to_test)} доменов")
    
    # 7. Environment variables check
    print("\n7️⃣ Проверка переменных окружения...")
    env_vars = ["TWITTERAPI_IO_KEY", "REDIS_URL"]
    env_ok = True
    for var in env_vars:
        value = os.getenv(var)
        if value:
            print(f"✅ {var} установлена (длина: {len(value)} символов)")
        else:
            print(f"❌ {var} не установлена")
            env_ok = False
    tests.append(("Environment Variables", env_ok))
    
    # Итоговая сводка
    print("\n" + "="*60)
    print("📊 РЕЗУЛЬТАТЫ ДИАГНОСТИКИ")
    print("="*60)
    
    passed = 0
    for test_name, result in tests:
        status = "✅ ОК" if result else "❌ ОШИБКА"
        print(f"{test_name:.<30} {status}")
        if result:
            passed += 1
    
    print(f"\nОбщий результат: {passed}/{len(tests)} тестов пройдено")
    
    if passed < len(tests):
        print("\n🛠️ РЕКОМЕНДАЦИИ ПО ИСПРАВЛЕНИЮ:")
        if not any(result for test_name, result in tests if "DNS" in test_name):
            print("• DNS проблемы - попробуйте:")
            print("  docker run --dns=8.8.8.8 ваш_контейнер")
            print("  или добавьте в docker-compose.yml:")
            print("  dns:")
            print("    - 8.8.8.8")
            print("    - 8.8.4.4")
        
        if not any(result for test_name, result in tests if "HTTP" in test_name):
            print("• HTTP проблемы - проверьте:")
            print("  - Настройки proxy в Docker")
            print("  - Firewall настройки")
            print("  - Сетевые политики")
        
        if not any(result for test_name, result in tests if "Environment" in test_name):
            print("• Переменные окружения - проверьте .env файл")
    
    return passed == len(tests)


def test_command_line_tools():
    """Тестирование через командную строку (только если утилиты доступны)"""
    print("\n8️⃣ Тестирование командной строки...")
    
    commands = [
        ("ping", ["ping", "-c", "1", "8.8.8.8"]),
        ("nslookup", ["nslookup", "google.com"]),
        ("curl", ["curl", "-I", "--max-time", "10", "https://google.com"]),
        ("wget", ["wget", "--spider", "--timeout=10", "https://google.com"])
    ]
    
    available_tools = 0
    for name, cmd in commands:
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            if result.returncode == 0:
                print(f"✅ {name} работает")
                available_tools += 1
            else:
                print(f"❌ {name} не работает: {result.stderr.strip()}")
        except subprocess.TimeoutExpired:
            print(f"⏰ {name} timeout")
        except FileNotFoundError:
            print(f"🔍 {name} не установлен")
        except Exception as e:
            print(f"❌ {name} ошибка: {e}")
    
    if available_tools == 0:
        print("ℹ️ Сетевые утилиты командной строки недоступны (это нормально для минимальных Docker образов)")
        print("💡 Рекомендуется добавить утилиты в Dockerfile:")
        print("   RUN apt-get update && apt-get install -y iputils-ping dnsutils curl wget")


async def test_redis_connection():
    """Тестирование подключения к Redis"""
    print("\n9️⃣ Тестирование подключения к Redis...")
    
    try:
        import redis.asyncio as redis
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        print(f"Подключение к Redis: {redis_url}")
        
        client = redis.from_url(redis_url)
        await client.ping()
        print("✅ Redis подключение работает")
        
        # Тест записи/чтения
        test_key = "test_docker_network"
        await client.set(test_key, "test_value", ex=60)
        value = await client.get(test_key)
        if value == b"test_value":
            print("✅ Redis запись/чтение работает")
        await client.delete(test_key)
        await client.close()
        
        return True
        
    except Exception as e:
        print(f"❌ Redis не работает: {e}")
        return False


async def main():
    """Основная функция"""
    
    print("🐳 Docker Network Diagnostics Tool v2.0")
    print("Проверяет сетевые проблемы внутри контейнера")
    print()
    
    # Async тесты
    network_ok = await test_basic_connectivity()
    
    # Redis тест
    redis_ok = await test_redis_connection()
    
    # Командная строка тесты
    test_command_line_tools()
    
    print("\n" + "="*60)
    if network_ok and redis_ok:
        print("🎉 Сеть и Redis работают нормально!")
        print("Если TwitterAPI.io все еще не работает, проверьте API ключ.")
    elif network_ok:
        print("⚠️ Сеть работает, но есть проблемы с Redis.")
    else:
        print("⚠️ Обнаружены сетевые проблемы.")
        print("Следуйте рекомендациям выше для исправления.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Диагностика прервана пользователем")
    except Exception as e:
        print(f"\n❌ Критическая ошибка: {e}")
        sys.exit(1) 