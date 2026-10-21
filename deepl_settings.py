"""DeepL official API translation settings, stored only in NAS /data."""
import json,os
from pathlib import Path

def settings_path(data):return Path(data)/"deepl_settings.json"

def load(data):
 p=settings_path(data)
 return json.loads(p.read_text("utf-8")) if p.exists() else {}

def public(data):
 x=load(data)
 return {"has_key":bool(x.get("api_key")),"plan":x.get("plan","free")}

def save(data,plan="free",api_key=None,clear_key=False):
 if plan not in ("free","pro"):raise ValueError("DeepL 账户类型无效")
 old=load(data)
 key="" if clear_key else (api_key.strip() if isinstance(api_key,str) and api_key.strip() else old.get("api_key",""))
 if not isinstance(key,str) or len(key)>500 or "\n" in key or "\r" in key:raise ValueError("DeepL API Key 格式无效")
 path=settings_path(data);path.parent.mkdir(parents=True,exist_ok=True)
 temp=path.with_suffix(".tmp")
 fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
 try:
  with os.fdopen(fd,"w",encoding="utf-8") as f:json.dump({"api_key":key,"plan":plan},f)
  os.chmod(temp,0o600);os.replace(temp,path)
 except BaseException:
  temp.unlink(missing_ok=True);raise
 return public(data)

def credentials(data):
 x=load(data)
 key=x.get("api_key","")
 if not key:raise ValueError("请先在网页设置 DeepL API Key")
 return key,x.get("plan","free")
