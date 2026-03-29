# dictionary.py
# Словарь с настройками кнопок и текстов

BOT_RESPONSES = {
    "FORBIDDEN": {"text": "🚫 Forbidden! Unauthorized user. Contact admin for help."},
    "WELCOME": {
        "text": "🏡 $Param1, система Dacha Vision AI приветствует вас!\nСтатус: ✅ На связи!",
        "buttons": [["📊 Статус"], ["📅 Сводка за 3 дня"], [["📸 Последнее событие"], "📡 Мониторинг"]]
    },
    "MENU": {"buttons": [["📊 Статус"], ["📅 Сводка за 3 дня"], [["📸 Последнее событие"], "📡 Мониторинг"]]}
}