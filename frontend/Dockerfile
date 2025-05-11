FROM node:18-alpine

# Установка рабочей директории
WORKDIR /app

# Установка зависимостей
COPY package.json package-lock.json ./
RUN npm ci

# Копирование исходного кода
COPY . .

# Порт для Next.js
EXPOSE 3000

# Запуск приложения в режиме разработки
CMD ["npm", "run", "dev"] 