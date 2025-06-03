#!/bin/bash

# test_docker_setup.sh
# Скрипт для тестирования Docker setup с диагностикой сети

set -e

echo "🐳 MrBets Docker Network Setup & Test Script"
echo "============================================="
echo ""

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Функция для логирования
log_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

log_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

log_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

log_error() {
    echo -e "${RED}❌ $1${NC}"
}

# Проверка предварительных условий
check_prerequisites() {
    log_info "Проверка предварительных условий..."
    
    # Проверка Docker
    if ! command -v docker &> /dev/null; then
        log_error "Docker не установлен"
        exit 1
    fi
    log_success "Docker установлен"
    
    # Проверка Docker Compose
    if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
        log_error "Docker Compose не установлен"
        exit 1
    fi
    log_success "Docker Compose установлен"
    
    # Проверка .env файла
    if [ ! -f .env ]; then
        log_warning ".env файл не найден, создаю из .env.example"
        if [ -f .env.example ]; then
            cp .env.example .env
            log_info "Отредактируйте .env файл с правильными API ключами"
        else
            log_error ".env.example не найден"
            exit 1
        fi
    fi
    log_success ".env файл найден"
    
    # Проверка API ключа TwitterAPI.io
    if ! grep -q "TWITTERAPI_IO_KEY=" .env || grep -q "TWITTERAPI_IO_KEY=$" .env; then
        log_warning "TWITTERAPI_IO_KEY не установлен в .env файле"
        log_info "Добавьте ваш TwitterAPI.io ключ в .env файл"
    else
        log_success "TWITTERAPI_IO_KEY настроен"
    fi
    
    echo ""
}

# Сборка Docker образов
build_images() {
    log_info "Сборка Docker образов..."
    
    if docker build -t mrbets-backend .; then
        log_success "Backend образ собран успешно"
    else
        log_error "Ошибка сборки backend образа"
        exit 1
    fi
    
    echo ""
}

# Запуск базовых тестов
run_basic_tests() {
    log_info "Запуск базовых тестов сети..."
    
    # Останавливаем существующие контейнеры
    docker-compose -f docker-compose.test.yml down 2>/dev/null || true
    
    # Запускаем тесты
    if docker-compose -f docker-compose.test.yml up --abort-on-container-exit backend-test; then
        log_success "Базовые тесты прошли успешно"
    else
        log_error "Базовые тесты провалились"
        
        # Показываем логи для диагностики
        log_info "Логи backend-test контейнера:"
        docker-compose -f docker-compose.test.yml logs backend-test
        
        return 1
    fi
    
    # Очистка
    docker-compose -f docker-compose.test.yml down
    
    echo ""
}

# Интерактивная диагностика
interactive_debug() {
    log_info "Запуск интерактивной диагностики..."
    log_info "Контейнер network-debug будет запущен в фоне для отладки"
    
    # Запускаем debug контейнер
    docker-compose -f docker-compose.test.yml up -d network-debug redis
    
    echo ""
    log_info "Доступные команды для диагностики:"
    echo "1. docker-compose -f docker-compose.test.yml exec network-debug ping google.com"
    echo "2. docker-compose -f docker-compose.test.yml exec network-debug nslookup api.twitterapi.io"
    echo "3. docker-compose -f docker-compose.test.yml exec network-debug curl -v https://api.twitterapi.io"
    echo "4. docker-compose -f docker-compose.test.yml exec network-debug traceroute api.twitterapi.io"
    echo ""
    
    log_info "Тестирование ping..."
    docker-compose -f docker-compose.test.yml exec network-debug ping -c 3 google.com || log_warning "Ping не работает"
    
    log_info "Тестирование DNS..."
    docker-compose -f docker-compose.test.yml exec network-debug nslookup api.twitterapi.io || log_warning "DNS resolution не работает"
    
    log_info "Тестирование HTTP..."
    docker-compose -f docker-compose.test.yml exec network-debug curl -I --max-time 10 https://api.twitterapi.io || log_warning "HTTP не работает"
    
    echo ""
    read -p "Нажмите Enter для завершения или Ctrl+C для продолжения отладки..."
    
    # Останавливаем debug контейнеры
    docker-compose -f docker-compose.test.yml down
}

# Функция очистки
cleanup() {
    log_info "Очистка ресурсов..."
    docker-compose -f docker-compose.test.yml down -v 2>/dev/null || true
    docker system prune -f --filter "label=project=mrbets" 2>/dev/null || true
}

# Основной процесс
main() {
    # Перехват сигналов для очистки
    trap cleanup EXIT
    
    case "${1:-all}" in
        "prereq")
            check_prerequisites
            ;;
        "build")
            check_prerequisites
            build_images
            ;;
        "test")
            check_prerequisites
            build_images
            run_basic_tests
            ;;
        "debug")
            check_prerequisites
            build_images
            interactive_debug
            ;;
        "all")
            check_prerequisites
            build_images
            if run_basic_tests; then
                log_success "🎉 Все тесты прошли успешно!"
                log_info "Twitter Fetcher готов к использованию"
            else
                log_warning "Тесты провалились, запускаю диагностику..."
                interactive_debug
            fi
            ;;
        *)
            echo "Использование: $0 [prereq|build|test|debug|all]"
            echo ""
            echo "  prereq - Проверка предварительных условий"
            echo "  build  - Сборка Docker образов"
            echo "  test   - Запуск тестов"
            echo "  debug  - Интерактивная диагностика"
            echo "  all    - Полный цикл (по умолчанию)"
            exit 1
            ;;
    esac
}

main "$@" 