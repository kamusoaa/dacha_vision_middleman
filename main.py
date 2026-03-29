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
    extra_text: str = ""
    type: str = "text"
    show_buttons: bool = True
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
        payload["file_name"] = f"photo_{file_id[:150]}.jpg"

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

    lookup_key = cmd.dictionary_key if cmd.dictionary_key else cmd.command_code

    response_config = BOT_RESPONSES.get(lookup_key)
    if not response_config:
        return {"status": "error", "message": f"Key '{lookup_key}' not found in dictionary"}

    text = response_config["text"]
    if cmd.extra_text:
        text += f"\n\n{cmd.extra_text}"

    reply_markup_dict = None
    if response_config.get("buttons"):
        reply_markup_dict = {"keyboard": response_config["buttons"], "resize_keyboard": True}

    results = []

    for target_id in cmd.chat_id:
        try:

            if cmd.type == "photo" and cmd.file_base64:
                if len(cmd.file_base64) > 1:
                    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMediaGroup"
                    media, files = [], {}

                    for i, b64 in enumerate(cmd.file_base64[:150]):

                        name = cmd.file_name[i] if i < len(cmd.file_name) else f"img_{i}.jpg"
                        files[name] = (name, io.BytesIO(base64.b64decode(b64)))
                        item = {"type": "photo", "media": f"attach://{name}"}
                        
                        if i == 0: 
                            item["caption"] = text
                        media.append(item)
                    res = requests.post(url, data={"chat_id": target_id, "media": json.dumps(media)}, files=files)

                    if reply_markup_dict and cmd.show_buttons:
                        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", 
                                      json={"chat_id": target_id, "text": "...", "reply_markup": reply_markup_dict})
                else:

                    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
                    name = cmd.file_name[0] if cmd.file_name else "photo.jpg"
                    files = {"photo": (name, io.BytesIO(base64.b64decode(cmd.file_base64[0])))}
                    data = {"chat_id": target_id, "caption": text}

                    if reply_markup_dict: 
                        data["reply_markup"] = json.dumps(reply_markup_dict)
                    res = requests.post(url, data=data, files=files)

            elif cmd.type == "document" and cmd.file_base64:

                if len(cmd.file_base64) > 1:

                    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMediaGroup"
                    media, files = [], {}

                    for i, b64 in enumerate(cmd.file_base64[:150]):
                        name = cmd.file_name[i] if i < len(cmd.file_name) else f"doc_{i}.dat"
                        files[name] = (name, io.BytesIO(base64.b64decode(b64)))
                        
                        item = {"type": "document", "media": f"attach://{name}"}
                        if i == 0: 
                            item["caption"] = text
                        media.append(item)

                    res = requests.post(url, data={"chat_id": target_id, "media": json.dumps(media)}, files=files)

                    if reply_markup_dict and cmd.show_buttons:
                        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", 
                                      json={"chat_id": target_id, "text": "...", "reply_markup": reply_markup_dict})
                else:

                    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument"
                    name = cmd.file_name[0] if cmd.file_name else "file.dat"
                    files = {"document": (name, io.BytesIO(base64.b64decode(cmd.file_base64[0])))}
                    data = {"chat_id": target_id, "caption": text}

                    if reply_markup_dict: 
                        data["reply_markup"] = json.dumps(reply_markup_dict)
                    res = requests.post(url, data=data, files=files)

            else:

                url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
                payload = {"chat_id": target_id, "text": text}

                if reply_markup_dict: 
                    payload["reply_markup"] = reply_markup_dict
                res = requests.post(url, json=payload)

            results.append({"chat_id": target_id, "status": res.status_code})

            time.sleep(0.04)

        except Exception as e:
            results.append({"chat_id": target_id, "status": "error", "error": str(e)})

    return {"status": "completed", "details": results}