
import os
import base64
import requests
import json
from fastapi import FastAPI, Request
from pydantic import BaseModel
from fastapi import BackgroundTasks
from responses import BOT_RESPONSES

app = FastAPI()

BOT_TOKEN = os.getenv("TOKEN")
URL_1C = os.getenv("URL_1C")

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
    
    payload = {
        "user_id": user_info.get("id"), 
        "username": user_info.get("username"), 
        "first_name": user_info.get("first_name"),
        "last_name": user_info.get("last_name") or "", 
        "chat_id": chat_id,
        "date": msg.get("date"),
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
