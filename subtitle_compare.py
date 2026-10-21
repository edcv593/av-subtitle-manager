"""Time-aligned subtitle evidence for text-only Chinese proofreading.

Never reads media bytes. Only compares matching subtitle cue intervals.
Unknown alignment is intentionally omitted rather than guessed.
"""
import re
import json
import urllib.request
import urllib.error
from pathlib import Path
import timeline

SUPPORTED={"srt","vtt","ass","ssa"}
HAN=re.compile(r"[\u3400-\u9fff]")
JAPANESE=re.compile(r"[\u3040-\u30ff]")
TIME=re.compile(r"\d{1,2}:\d{2}:\d{2}[,.]\d{1,3}\s*-->")

def entries(raw,ext):
 ext=ext.lower()
 if ext not in SUPPORTED:raise ValueError("不支持的字幕格式")
 text=timeline.decode(raw)
 intervals=timeline.cues(raw,ext)
 if not text or not intervals:raise ValueError("字幕时间轴无效")
 bodies=[]
 if ext in ("srt","vtt"):
  for block in re.split(r"\r?\n\s*\r?\n",text):
   lines=block.splitlines()
   indices=[i for i,line in enumerate(lines) if TIME.search(line)]
   if not indices:continue
   i=indices[0]
   value=" ".join(v.strip() for v in lines[i+1:] if v.strip() and not v.strip().startswith(("NOTE ","STYLE","REGION")))
   bodies.append(value)
 else:
  events=False;format_fields=[]
  for line in text.splitlines():
   line=line.strip()
   if line.startswith("["):events=line.lower()=="[events]";continue
   if not events:continue
   if line.lower().startswith("format:"):format_fields=[v.strip().lower() for v in line.split(":",1)[1].split(",")];continue
   if not line.lower().startswith("dialogue:"):continue
   if not format_fields or "text" not in format_fields:raise ValueError("ASS 缺少 Text 格式")
   fields=line.split(":",1)[1].lstrip().split(",",len(format_fields)-1)
   if len(fields)!=len(format_fields):raise ValueError("ASS 事件字段无效")
   bodies.append(fields[format_fields.index("text")].replace(r"\N"," ").replace(r"\n"," "))
 if len(bodies)!=len(intervals):raise ValueError("字幕正文与时间轴数量不符")
 return [{"start":a,"end":b,"text":v} for (a,b),v in zip(intervals,bodies)]

def language(value):
 if JAPANESE.search(value):return "ja"
 if HAN.search(value):return "zh"
 return "unknown"

def match(source,reference,shift=0,min_overlap=0.50):
 """Best overlap match with duration-normalized confidence; unmatched cues excluded."""
 if not -120<=shift<=120:raise ValueError("参考时间偏移超过安全范围")
 out=[]
 for cue in source:
  span=max(0.001,cue["end"]-cue["start"])
  options=[]
  for r in reference:
   start=r["start"]+shift;end=r["end"]+shift
   overlap=max(0,min(cue["end"],end)-max(cue["start"],start))
   denom=max(span,end-start,0.001)
   score=overlap/denom
   if score>=min_overlap and r["text"].strip():options.append((score,r))
  options.sort(key=lambda item:item[0],reverse=True)
  # Reject ties: alternative cue segmentation can make evidence misleading.
  if options and (len(options)==1 or options[0][0]-options[1][0]>=0.15):
   out.append({"cue":cue,"reference":options[0][1],"confidence":round(options[0][0],2)})
  else:out.append({"cue":cue,"reference":None,"confidence":0})
 return out

def review_batch(primary_raw,primary_ext,refs,offset=0,max_cues=25):
 """Return aligned evidence only; refs contain (label, bytes, extension, offset) tuples."""
 source=entries(primary_raw,primary_ext)
 if not isinstance(offset,int) or isinstance(offset,bool) or offset<0 or offset>len(source):raise ValueError("批次偏移无效")
 if len(refs)>3:raise ValueError("最多使用三个参考字幕")
 chunk=source[offset:offset+max_cues]
 aligned=[]
 for label,raw,ext,shift in refs:
  if not isinstance(label,str) or len(label)>100:raise ValueError("参考名称无效")
  aligned.append((label,match(chunk,entries(raw,ext),shift)))
 rows=[]
 for i,cue in enumerate(chunk):
  evidence=[]
  for label,items in aligned:
   result=items[i]
   if result["reference"]:
    evidence.append({"source":label,"text":result["reference"]["text"][:500],"confidence":result["confidence"]})
  rows.append({"index":offset+i,"start":cue["start"],"end":cue["end"],"chinese":cue["text"][:500],"references":evidence})
 next_offset=offset+len(chunk)
 return {"rows":rows,"next_offset":next_offset,"done":next_offset>=len(source),"total":len(source)}

def ai_review(rows,api_key,model,endpoint,allowed_lines):
 """AI outputs audited suggestions only. Exact original text and unique-line checks."""
 if not api_key:raise ValueError("请先配置 DeepSeek API Key")
 evidence=[r for r in rows if r["references"] and r["chinese"]]
 if not evidence:return []
 prompt=("你是中文字幕校对员。已存在简体中文字幕，禁止整片重译。"
         "仅依据时间轴匹配的日语或其他中文参考提供有根据的纠错建议；"
         "不能确认原文含义、参考相互冲突或对齐不可靠时保留原译。"
         "只返回 JSON 对象 {\"suggestions\":[{\"index\":0,\"before\":\"完整原字幕\",\"after\":\"完整建议\",\"reason\":\"依据\"}]}，"
         "最多10条。不改变时间戳，不合并不同条目。\n字幕和证据：\n"+
         json.dumps(evidence,ensure_ascii=False))
 body=json.dumps({"model":model,"messages":[{"role":"user","content":prompt}],"response_format":{"type":"json_object"},"temperature":0.2,"max_tokens":1800}).encode("utf-8")
 req=urllib.request.Request(endpoint,data=body,headers={"Authorization":"Bearer "+api_key,"Content-Type":"application/json"},method="POST")
 try:
  with urllib.request.urlopen(req,timeout=45) as resp:
   raw=resp.read(120000)
 except urllib.error.HTTPError as exc:
  if exc.code==401:raise ValueError("AI API Key 无效（HTTP 401）") from None
  if exc.code==402:raise ValueError("AI 账户额度不足（HTTP 402）") from None
  if exc.code==429:raise ValueError("AI 请求被限流（HTTP 429），请稍后重试") from None
  raise ValueError("AI 服务返回 HTTP "+str(exc.code)) from None
 except (urllib.error.URLError,TimeoutError) as exc:
  raise ValueError("AI 服务网络连接或请求超时："+str(exc)[:100]) from None
 if not raw.strip():raise ValueError("AI 服务返回空 HTTP 响应，请检查 API 地址和代理配置")
 try:response=json.loads(raw)
 except (ValueError,UnicodeError) as exc:raise ValueError("AI 服务返回非 JSON 内容，请检查 API 地址和服务商配置") from exc
 if not isinstance(response,dict) or not isinstance(response.get("choices"),list) or not response["choices"]:
  raise ValueError("AI 服务响应缺少 choices，请检查模型是否支持聊天接口")
 choice=response["choices"][0]
 content=choice.get("message",{}).get("content") if isinstance(choice,dict) else None
 if not isinstance(content,str) or not content.strip():
  reason=choice.get("finish_reason","unknown") if isinstance(choice,dict) else "unknown"
  raise ValueError("AI 返回空的校对内容（finish_reason="+str(reason)[:40]+"）；可能是模型未输出正文或输出长度不足")
 content=content.strip()
 if content.startswith("```"):
  content=re.sub(r"^\x60{3}(?:json)?\\s*|\\s*\x60{3}$","",content,flags=re.I).strip()
 try:parsed=json.loads(content)
 except ValueError as exc:raise ValueError("AI 校对正文不是有效 JSON，建议更换模型或增加输出额度") from exc
 if not isinstance(parsed,dict):raise ValueError("AI 校对结果必须是 JSON 对象")
 items=parsed.get("suggestions",[])
 if not isinstance(items,list):raise ValueError("AI 建议列表格式无效")
 lookup={r["index"]:r for r in evidence}
 result=[];seen=set()
 for item in items[:10]:
  if not isinstance(item,dict) or not isinstance(item.get("index"),int):continue
  row=lookup.get(item["index"]);before=item.get("before");after=item.get("after");reason=item.get("reason","")
  if not row or row["index"] in seen or before!=row["chinese"] or allowed_lines.count(before)!=1:continue
  if not isinstance(after,str) or not after.strip() or after==before or len(after)>1000 or "\n" in after or "\r" in after:continue
  if not isinstance(reason,str) or not reason.strip():continue
  seen.add(row["index"])
  result.append({"index":row["index"],"before":before,"after":after,"reason":reason[:240],"references":row["references"]})
 return result
