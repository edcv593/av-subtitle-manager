"""Server-side AI provider settings. Keys are never returned to browsers."""
import json
import os
from pathlib import Path

PROVIDERS={
 "deepseek":{"endpoint":"https://api.deepseek.com/chat/completions","model":"deepseek-flash"},
 "openai":{"endpoint":"https://api.openai.com/v1/chat/completions","model":"gpt-4o-mini"}
}

def settings_path(data_dir):return Path(data_dir)/"ai_provider.json"

def load(data_dir):
 path=settings_path(data_dir)
 if not path.exists():return {}
 return json.loads(path.read_text(encoding="utf-8"))

def public(data_dir):
 settings=load(data_dir)
 provider=settings.get("provider","deepseek")
 if provider not in PROVIDERS:provider="deepseek"
 return {"provider":provider,"model":settings.get("model",PROVIDERS[provider]["model"]),"has_key":bool(settings.get("api_key"))}

def save(data_dir,provider,model,api_key=None,clear_key=False):
 if provider not in PROVIDERS:raise ValueError("不支持的 AI 服务商")
 if not isinstance(model,str) or not model or len(model)>100 or not all(c.isalnum() or c in "._-" for c in model):
  raise ValueError("模型名称无效")
 previous=load(data_dir)
 key="" if clear_key else (api_key.strip() if isinstance(api_key,str) and api_key.strip() else previous.get("api_key",""))
 if len(key)>500 or "\n" in key or "\r" in key:raise ValueError("API Key 格式无效")
 path=settings_path(data_dir)
 path.parent.mkdir(parents=True,exist_ok=True)
 temp=path.with_name(path.name+".tmp")
 fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
 try:
  with os.fdopen(fd,"w",encoding="utf-8") as stream:json.dump({"provider":provider,"model":model,"api_key":key},stream)
  os.chmod(temp,0o600)
  os.replace(temp,path)
 except BaseException:
  temp.unlink(missing_ok=True)
  raise
 return public(data_dir)

def credentials(data_dir):
 settings=load(data_dir)
 provider=settings.get("provider","deepseek")
 if provider not in PROVIDERS:raise ValueError("未知 AI 服务商")
 return settings.get("api_key",""),settings.get("model",PROVIDERS[provider]["model"]),PROVIDERS[provider]["endpoint"]
