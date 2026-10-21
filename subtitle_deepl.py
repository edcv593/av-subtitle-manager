"""DeepL official API translator for Japanese subtitle text (not video/audio)."""
import json
import urllib.request
import urllib.error

URLS={"free":"https://api-free.deepl.com/v2/translate","pro":"https://api.deepl.com/v2/translate"}

def translate(text,api_key,plan="free",opener=None):
 if plan not in URLS:raise ValueError("DeepL 账户类型无效")
 if not isinstance(api_key,str) or not api_key:raise ValueError("缺少 DeepL API Key")
 if not isinstance(text,str) or not text.strip() or len(text)>1000:raise ValueError("DeepL 文本为空或超过长度限制")
 body=json.dumps({"text":[text],"source_lang":"JA","target_lang":"ZH","preserve_formatting":True},ensure_ascii=False).encode("utf-8")
 req=urllib.request.Request(URLS[plan],data=body,headers={"Authorization":"DeepL-Auth-Key "+api_key,"Content-Type":"application/json"},method="POST")
 if opener is None:opener=urllib.request.urlopen
 try:
  with opener(req,timeout=25) as resp:result=json.loads(resp.read(100000))
 except urllib.error.HTTPError as exc:
  if exc.code==403:raise ValueError("DeepL API Key 无效或无权限") from None
  if exc.code==456:raise ValueError("DeepL 字符额度已用尽") from None
  if exc.code==429:raise ValueError("DeepL 请求频率受限，请稍后重试") from None
  raise ValueError("DeepL HTTP "+str(exc.code)) from None
 except (urllib.error.URLError,TimeoutError) as exc:raise ValueError("DeepL 网络请求失败："+str(exc.reason if hasattr(exc,"reason") else exc)[:80]) from None
 except (json.JSONDecodeError,UnicodeError) as exc:raise ValueError("DeepL 响应不是有效 JSON") from exc
 translations=result.get("translations") if isinstance(result,dict) else None
 if not isinstance(translations,list) or not translations or not isinstance(translations[0],dict) or not isinstance(translations[0].get("text"),str) or not translations[0]["text"].strip():
  raise ValueError("DeepL 返回格式异常")
 return translations[0]["text"]
