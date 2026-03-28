
import os
import base64
import requests
import json
import io
from fastapi import FastAPI, Request
from pydantic import BaseModel
from fastapi import BackgroundTasks
from dictionary import BOT_RESPONSES
from datetime import datetime

app = FastAPI()

BOT_TOKEN = os.getenv("TOKEN")
URL_1C = os.getenv("URL_1C")

class CommandFrom1C(BaseModel):
    chat_id: int
    command_code: str
    extra_text: str = ""
    file_base64: str = ""
    file_name: str = ""

def download_file_as_base64(file_id):

    path_url = f"https://api.telegram.org/bot{BOT_TOKEN}/getFile?file_id={file_id}"
    path_resp = requests.get(path_url).json()
    
    if not path_resp.get("ok"):
        return None
        
    file_path = path_resp["result"]["file_path"]
    
    download_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
    file_content = requests.get(download_url).content
    
    return base64.b64encode(file_content).decode('utf-8')

@app.get("/ping")
async def ping():
    return {"status": "ok", "service": "Dacha_Vision_Middleman", "active": True}

@app.post("/webhook")
async def handle_webhook(request: Request):

    update = await request.json()
    
    if "message" not in update:
        return {"status": "ignored"}

    msg = update["message"]
    chat_id = msg["chat"]["id"]
    user_info = msg.get("from", {})

    unix_date = msg.get("date")
    dt_object = datetime.fromtimestamp(unix_date)
    readable_date = dt_object.strftime("%Y-%m-%dT%H:%M:%S")
    
    payload = {
        "user_id": user_info.get("id"), 
        "username": user_info.get("username"), 
        "first_name": user_info.get("first_name"),
        "last_name": user_info.get("last_name") or "", 
        "chat_id": chat_id,
        "date": readable_date,
        "type": "text",
        "text": msg.get("text", ""),
        "file_data": None or "",
        "file_name": None or ""
    }

    if "photo" in msg:
        payload["type"] = "photo"
        file_id = msg["photo"][-1]["file_id"]
        payload["file_data"] = download_file_as_base64(file_id)
        payload["file_name"] = f"photo_{file_id[:50]}.jpg"

    elif "document" in msg:
        payload["type"] = "document"
        doc = msg["document"]
        payload["file_data"] = download_file_as_base64(doc["file_id"])
        payload["file_name"] = doc.get("file_name", "file.dat")

    try:
        response = requests.post(URL_1C, json=payload, timeout=15)
        return {"status": "sent_to_1c", "1c_response": response.status_code}
    except Exception as e:
        return {"status": "error", "reason": str(e)}

@app.post("/send_to_bot")
async def send_to_bot(cmd: CommandFrom1C):

    response_config = BOT_RESPONSES.get(cmd.command_code)

    if not response_config:
        return {"status": "error", "message": "Unknown command code"}

    text = response_config["text"]
    if cmd.extra_text:
        text += f"\n\n{cmd.extra_text}"

    reply_markup = None
    if response_config.get("buttons"):
        reply_markup = json.dumps({
            "keyboard": response_config["buttons"],
            "resize_keyboard": True
        })

    if cmd.file_base64:

        file_bytes = base64.b64decode(cmd.file_base64)

        file_io = io.BytesIO(file_bytes)
        file_io.name = cmd.file_name or "file.jpg"

        is_photo = file_io.name.lower().endswith(('.jpg', '.jpeg', '.png'))
        method = "sendPhoto" if is_photo else "sendDocument"
        file_type = "photo" if is_photo else "document"

        url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
        
        files = {file_type: (file_io.name, file_io)}
        data = {
            "chat_id": cmd.chat_id,
            "caption": text, # В методах с файлами текст сообщения идет в поле caption
            "reply_markup": reply_markup
        }
        
        tg_res = requests.post(url, data=data, files=files)
    else:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": cmd.chat_id,
            "text": text,
            "reply_markup": reply_markup
        }
        tg_res = requests.post(url, json=payload)

    print(f"TG RESPONSE: {tg_res.status_code} - {tg_res.text}")
    
    return {"status": "ok", "tg_code": tg_res.status_code}
