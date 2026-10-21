"""Text-only subtitle optimization. Never accesses video or changes timing lines."""
import difflib
import hashlib
import json
import os
import re
import urllib.request
from pathlib import Path

try:
 from opencc import OpenCC
except ImportError:
 OpenCC=None

TIMING=re.compile(r"\s*\d{1,2}:\d{2}:\d{2}[,.]\d{1,3}\s*-->")
ASS_TEXT=re.compile(r"^\s*Dialogue\s*:",re.I)
CJK=re.compile(r"[\u3400-\u9fff]")
CONVERSION=None

def converter():
 global CONVERSION
 if OpenCC is None:raise ValueError("OpenCC 未安装，无法转换繁体")
 if CONVERSION is None:CONVERSION=OpenCC("t2s")
 return CONVERSION

def normalize_text(text,simplify=True,punctuation=True):
 if simplify:text=converter().convert(text)
 if punctuation:
  text=text.replace("\u3000"," ").replace("\u00a0"," ")
  text=re.sub(r"(?<=[\u3400-\u9fff])\s+(?=[\u3400-\u9fff])","",text)
  text=re.sub(r" {2,}"," ",text)
  text=re.sub(r"([，。！？；：])\1+",r"\1",text)
  text=re.sub(r"\.\.\.{2,}","……",text)
 return text

def edit_cues(raw,ext,transform):
 """Edit text payloads only; preserve original line endings and timestamp/header bytes."""
 text=raw.decode("utf-8-sig")
 if text.startswith("\ufeff"):text=text[1:]
 newline="\r\n" if "\r\n" in text else "\n"
 result=[];changes=[]
 lines=text.splitlines(keepends=True)
 in_ass_events=False
 for line in lines:
  body=line.rstrip("\r\n");ending=line[len(body):]
  original=body
  if ext.lower() in ("srt","vtt"):
   stripped=body.strip()
   is_meta=(not stripped or stripped.isdecimal() or "-->" in body or stripped=="WEBVTT" or stripped.startswith(("NOTE ","STYLE","REGION","X-TIMESTAMP-MAP")))
   if not is_meta and not (stripped.startswith(("Kind:","Language:"))):
    body=transform(body)
  elif ext.lower() in ("ass","ssa"):
   if body.strip().lower()=="[events]":in_ass_events=True
   elif body.startswith("[") and body.endswith("]"):in_ass_events=False
   if in_ass_events and ASS_TEXT.match(body):
    parts=body.split(",",9)
    if len(parts)==10:parts[-1]=transform(parts[-1]);body=",".join(parts)
  else:raise ValueError("不支持的字幕格式")
  if body!=original:changes.append({"before":original,"after":body})
  result.append(body+ending)
 encoded="".join(result).encode("utf-8-sig" if raw.startswith(b"\xef\xbb\xbf") else "utf-8")
 return encoded,changes

def optimize(raw,ext,simplify=True,punctuation=True,replacements=None):
 replacements=replacements or {}
 if not isinstance(replacements,dict) or len(replacements)>200:raise ValueError("修改数量过多")
 def transform(line):
  new=normalize_text(line,simplify,punctuation)
  if line in replacements:new=replacements[line]
  if not isinstance(new,str) or "\n" in new or "\r" in new or len(new)>1500:raise ValueError("修改后的字幕正文无效")
  return new
 data,changes=edit_cues(raw,ext,transform)
 if len(changes)>10000:raise ValueError("修改条数过多")
 return data,changes

def digest(raw):return hashlib.sha256(raw).hexdigest()

def preview(raw,ext,simplify=True,punctuation=True,replacements=None):
 data,changes=optimize(raw,ext,simplify,punctuation,replacements)
 return {"original_sha256":digest(raw),"optimized_sha256":digest(data),"changed":len(changes),"changes":changes[:60],"truncated":len(changes)>60,"original_size":len(raw),"optimized_size":len(data)}

def ai_suggestions(raw,ext,api_key,model="gpt-4o-mini",endpoint="https://api.openai.com/v1/chat/completions"):
 """Optional external text-only suggestions. Never automatically edits files."""
 if not api_key:raise ValueError("未配置字幕润色 API Key")
 _,changes=edit_cues(raw,ext,lambda s:s)
 # Collect text from the subtitle using a deliberately bounded window.
 sample=raw.decode("utf-8-sig","replace")[:12000]
 prompt=("你是中文字幕编辑。仅根据提供的字幕文本和上下文建议更通顺的简体中文；"
         "无法从字幕文本验证真实场景或原语言准确性，不要臆造。"
         "只输出JSON对象，格式为{\"suggestions\":[{\"before\":\"原文\",\"after\":\"建议\"}]}。"
         "最多10条，每条before必须与原文完整一行相同，不修改时间轴。\n"+sample)
 payload=json.dumps({"model":model,"messages":[{"role":"user","content":prompt}],"response_format":{"type":"json_object"},"temperature":0.2,"max_tokens":1200}).encode()
 request=urllib.request.Request(endpoint,data=payload,headers={"Authorization":"Bearer "+api_key,"Content-Type":"application/json"},method="POST")
 with urllib.request.urlopen(request,timeout=40) as response:
  answer=json.loads(response.read(100000))
 body=json.loads(answer["choices"][0]["message"]["content"])
 suggestions=body.get("suggestions",[])
 if not isinstance(suggestions,list):raise ValueError("AI 响应格式错误")
 valid_lines=set(raw.decode("utf-8-sig","replace").splitlines())
 result=[]
 for item in suggestions[:10]:
  if not isinstance(item,dict):continue
  before=item.get("before");after=item.get("after")
  if isinstance(before,str) and before in valid_lines and isinstance(after,str) and 0<len(after)<1500 and "\n" not in after and "\r" not in after and before!=after and "-->" not in before:
   result.append({"before":before,"after":after})
 return result
