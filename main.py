import os
import base64
import requests
import json
import io
import time
from fastapi import FastAPI, Request
from pydantic import BaseModel
from fastapi import BackgroundTasks
from dictionary import BOT_RESPONSES
from datetime import datetime
from typing import List, Optional

app = FastAPI()

BOT_TOKEN = os.getenv("TOKEN")
URL_1C = os.getenv("URL_1C")

class CommandFrom1C(BaseModel):
    chat_id: List[int]
    command_code: str
    dictionary_key: Optional[str] = ""
    params: List[str] = []
    type: str = "text"
    show_buttons: bool = True
    extra_text: str = ""
    file_base64: List[str] = []
    file_name: List[str] = []

def download_file_as_base64(file_id):
    path_url = f"https://api.telegram.org/bot{BOT_TOKEN}/getFile?file_id={file_id}"
    path_resp = requests.get(path_url).json()
    
    if not path_resp.get("ok"):
        return None
        
    file_path = path_resp["result"]["file_path"]
    
    download_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
    file_content = requests.get(download_url).content
    
    return base64.b64encode(file_content).decode('utf-8')

def apply_params(source, params: List[str]):

    if not params:
        return source
    
    if isinstance(source, str):
        res = source
        for i, val in enumerate(params):
            placeholder = f"Param{i+1}"
            res = res.replace(placeholder, str(val))
        return res
    
    if isinstance(source, list):
        return [[apply_params(button, params) for button in row] for row in source]
    
    return source

@app.get("/ping")
async def ping():
    return {"status": "ok", "service": "Dacha_Vision_Middleman", "active": True}

@app.post("/webhook")
async def handle_webhook(request: Request):

    update = await request.json()
    print(f"📩 Получен вебхук от ТГ: {update}") # Видим, что прислал Телеграм
    
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
        "username": user_info.get("username") or "", 
        "first_name": user_info.get("first_name") or "",
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
        payload["file_name"] = f"photo_{file_id[:150]}.jpg"

    elif "document" in msg:
        payload["type"] = "document"
        doc = msg["document"]
        payload["file_data"] = download_file_as_base64(doc["file_id"])
        payload["file_name"] = doc.get("file_name", "file.dat")

    try:
        response = requests.post(URL_1C, json=payload, timeout=15)

        print(f"🔌 Ответ от 1С: Статус {response.status_code} | Тело: {response.text}")
        return {"status": "sent_to_1c", "1c_response": response.status_code}
    except Exception as e:
        print(f"❌ Ошибка при пересылке в 1С: {str(e)}")
        return {"status": "error", "reason": str(e)}

@app.post("/send_to_bot")
async def send_to_bot(cmd: CommandFrom1C):
    
    cmd_data = cmd.dict()
    dict_key = cmd_data.get("dictionary_key")
    comm_code = cmd_data.get("command_code")
    lookup_key = dict_key if dict_key else comm_code
    
    response_config = BOT_RESPONSES.get(lookup_key)
    if not response_config:
        print(f"❌ Ошибка: Ключ '{lookup_key}' не найден в dictionary.py")
        return {"status": "error", "message": f"Key '{lookup_key}' not found"}

    raw_text = response_config.get("text", "")
    main_text = apply_params(raw_text, cmd.params) if raw_text else ""

    message_parts = []
    
    if main_text.strip():
        message_parts.append(main_text.strip())
        
    if cmd.extra_text and cmd.extra_text.strip():
        message_parts.append(cmd.extra_text.strip())
        
    text = "\n\n".join(message_parts)

    reply_markup_dict = None
    if response_config.get("buttons"):
        processed_buttons = apply_params(response_config["buttons"], cmd.params)
        reply_markup_dict = {"keyboard": processed_buttons, "resize_keyboard": True}

    results = []

    for target_id in cmd.chat_id:
        try:
            res = None

            if cmd.type == "photo" and cmd.file_base64:
                if len(cmd.file_base64) > 1:
                    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMediaGroup"
                    media, files = [], {}
                    
                    for i, b64 in enumerate(cmd.file_base64[:10]):
                        name = cmd.file_name[i][:150] if i < len(cmd.file_name) else f"img_{i}.jpg"
                        files[name] = (name, io.BytesIO(base64.b64decode(b64)))
                        
                        item = {
                            "type": "photo", 
                            "media": f"attach://{name}", 
                            "parse_mode": "HTML"
                        }
                        
                        if i == 0: 
                            item["caption"] = text[:1024]
                        media.append(item)
                    
                    res = requests.post(url, data={"chat_id": target_id, "media": json.dumps(media)}, files=files)

                else:
                    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
                    name = cmd.file_name[0][:150] if cmd.file_name else "photo.jpg"

                    files = {"photo": (name, io.BytesIO(base64.b64decode(cmd.file_base64[0])))}
                    data = {"chat_id": target_id, "caption": text[:1024], "parse_mode": "HTML"}

                    if reply_markup_dict and cmd.show_buttons: 
                        data["reply_markup"] = json.dumps(reply_markup_dict)
                    res = requests.post(url, data=data, files=files)

            elif cmd.type == "document" and cmd.file_base64:
                if len(cmd.file_base64) > 1:
                    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMediaGroup"
                    media, files = [], {}

                    for i, b64 in enumerate(cmd.file_base64[:10]):
                        name = cmd.file_name[i][:150] if i < len(cmd.file_name) else f"doc_{i}.dat"
                        files[name] = (name, io.BytesIO(base64.b64decode(b64)))
                        
                        item = {
                            "type": "document", 
                            "media": f"attach://{name}", 
                            "parse_mode": "HTML"
                        }
                        
                        if i == 0: 
                            item["caption"] = text[:1024]
                        media.append(item)
                    
                    res = requests.post(url, data={"chat_id": target_id, "media": json.dumps(media)}, files=files)
                else:
                    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument"
                    name = cmd.file_name[0][:150] if cmd.file_name else "file.dat"
                    files = {"document": (name, io.BytesIO(base64.b64decode(cmd.file_base64[0])))}
                    data = {"chat_id": target_id, "caption": text[:1024], "parse_mode": "HTML"}
                    if reply_markup_dict and cmd.show_buttons: 
                        data["reply_markup"] = json.dumps(reply_markup_dict)
                    res = requests.post(url, data=data, files=files)

            else:
                url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
                payload = {"chat_id": target_id, "text": text, "parse_mode": "HTML"}

                if reply_markup_dict and cmd.show_buttons: 
                    payload["reply_markup"] = reply_markup_dict
                res = requests.post(url, json=payload)

            if res is not None:
                print(f"📢 TG LOG [{target_id}]: Status {res.status_code} | Response: {res.text}")
                results.append({"chat_id": target_id, "status": res.status_code, "tg_msg": res.text})
            
            time.sleep(0.05)

        except Exception as e:
            print(f"❌ Ошибка на {target_id}: {str(e)}")
            results.append({"chat_id": target_id, "status": "error", "error": str(e)})

    return {"status": "completed", "details": results}