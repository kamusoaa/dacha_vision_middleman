# Используем стабильную и легкую версию Python
FROM python:3.10-slim

# Устанавливаем рабочую директорию внутри контейнера
WORKDIR /app

# Копируем список зависимостей
COPY requirements.txt .

# Устанавливаем библиотеки
RUN pip install --no-cache-dir -r requirements.txt

# Копируем основной файл с кодом
COPY main.py .

# Открываем порт 8000 (стандарт для FastAPI)
EXPOSE 8000

# Запускаем сервер uvicorn
# 0.0.0.0 позволяет принимать запросы извне контейнера
CMD ["uvicorn", "main.py:app", "--host", "0.0.0.0", "--port", "8000"]