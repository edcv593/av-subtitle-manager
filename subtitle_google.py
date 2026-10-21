"""Experimental, rate-limited Google web translation for subtitle *text only*.

This unofficial endpoint can change, throttle or refuse requests. No media reads.
"""
import json
import random
import re
import time
import urllib.parse
import urllib.request
import urllib.error

ENDPOINT="https://translate.googleapis.com/translate_a/single"
MAX_CHARS=800
MIN_INTERVAL=1.5

def google_translate(text, opener=None, sleep=time.sleep, retries=2):
 if not isinstance(text,str) or not text.strip() or len(text)>MAX_CHARS:
  raise ValueError("翻译文本为空或超过单次长度限制")
 if opener is None:opener=urllib.request.urlopen
 query=urllib.parse.urlencode({"client":"gtx","sl":"ja","tl":"zh-CN","dt":"t","q":text})
 request=urllib.request.Request(ENDPOINT+"?"+query,headers={"User-Agent":"Mozilla/5.0","Accept":"application/json"})
 last=None
 for attempt in range(retries+1):
  try:
   with opener(request,timeout=20) as response:
    raw=response.read(100000)
   parsed=json.loads(raw)
   if not isinstance(parsed,list) or not parsed or not isinstance(parsed[0],list):
    raise ValueError("Google 翻译响应格式变化")
   result="".join(part[0] for part in parsed[0] if isinstance(part,list) and part and isinstance(part[0],str))
   if not result.strip():raise ValueError("Google 翻译返回空文本")
   return result
  except (urllib.error.URLError,TimeoutError,ValueError,json.JSONDecodeError) as exc:
   last=exc
   if attempt>=retries:break
   sleep(min(12,2**attempt*2)+random.uniform(0,0.5))
 raise ValueError("Google 免费翻译不可用或被限流："+str(last)[:100])

def translate_srt(raw,offset=0,max_cues=15,translator=google_translate,sleep=time.sleep):
 """Translate SRT by cue; return one bounded preview batch and a stable cue offset.

 Preserve index and time lines verbatim. Failed cues retain Japanese as fallback.
 """
 import timeline
 text=timeline.decode(raw)
 if text is None:raise ValueError("无法解码日语字幕")
 if not isinstance(offset,int) or isinstance(offset,bool) or offset<0:raise ValueError("无效字幕偏移")
 if not isinstance(max_cues,int) or not 1<=max_cues<=30:raise ValueError("批次大小无效")
 blocks=re.split(r"(\r?\n[ \t]*\r?\n)",text)
 entries=[];positions=[]
 for idx in range(0,len(blocks),2):
  block=blocks[idx]
  lines=block.splitlines(keepends=True)
  time_index=next((i for i,line in enumerate(lines) if "-->" in line),None)
  if time_index is not None and timeline.cues(block.encode("utf-8"),"srt"):
   entries.append((idx,lines,time_index))
 if not entries:raise ValueError("未找到有效 SRT 时间轴")
 if offset>len(entries):raise ValueError("偏移超过字幕总数")
 changes=[];failed=[]
 for cue_index in range(offset,min(len(entries),offset+max_cues)):
  idx,lines,time_index=entries[cue_index]
  for line_index in range(time_index+1,len(lines)):
   line=lines[line_index];body=line.rstrip("\r\n");ending=line[len(body):]
   if not body.strip() or re.fullmatch(r"<[^>]+>",body.strip()):continue
   if len(body)>MAX_CHARS:
    failed.append({"cue":cue_index+1,"reason":"单行超过翻译限制"});continue
   try:
    translated=translator(body)
    if not isinstance(translated,str) or not translated.strip() or "\n" in translated or "\r" in translated:raise ValueError("无效译文")
    lines[line_index]=translated+ending
    changes.append({"cue":cue_index+1,"before":body,"after":translated})
   except Exception as exc:
    failed.append({"cue":cue_index+1,"reason":str(exc)[:120]})
   sleep(MIN_INTERVAL)
  blocks[idx]="".join(lines)
 next_offset=min(len(entries),offset+max_cues)
 return {"translated_text":"".join(blocks),"changes":changes,"failed":failed,"next_offset":next_offset,"total":len(entries),"done":next_offset==len(entries)}

def retry_failed_srt(draft_raw,source_raw,failures,max_cues=2,translator=google_translate,sleep=time.sleep):
 """Retry failed cue lines only, preserving already translated text and timestamps."""
 import timeline
 draft=timeline.decode(draft_raw);original=timeline.decode(source_raw)
 if draft is None or original is None:raise ValueError("字幕编码无效")
 split_pattern=r"(\r?\n[ \t]*\r?\n)"
 db=re.split(split_pattern,draft);sb=re.split(split_pattern,original)
 if len(db)!=len(sb):raise ValueError("草稿与原字幕结构不同")
 positions=[]
 for i in range(0,len(sb),2):
  if timeline.cues(sb[i].encode("utf-8"),"srt"):positions.append(i)
 unique=sorted({int(f["cue"]) for f in failures if isinstance(f,dict) and isinstance(f.get("cue"),int) and 1<=f["cue"]<=len(positions)})
 if not unique:return {"translated_text":draft,"resolved":[],"remaining":[],"attempted":0}
 selected=set(unique[:max_cues]);remaining=[f for f in failures if f.get("cue") not in selected]
 resolved=[];retry_errors=[]
 for cue in unique[:max_cues]:
  idx=positions[cue-1]
  src_lines=sb[idx].splitlines(keepends=True);dst_lines=db[idx].splitlines(keepends=True)
  if len(src_lines)!=len(dst_lines):raise ValueError("字幕条目行数已变化")
  timing=next((j for j,line in enumerate(src_lines) if "-->" in line),None)
  if timing is None:continue
  had_error=False
  for j in range(timing+1,len(src_lines)):
   original_line=src_lines[j].rstrip("\r\n")
   current_line=dst_lines[j].rstrip("\r\n")
   if not original_line.strip() or current_line!=original_line:continue
   try:
    translated=translator(original_line)
    if not isinstance(translated,str) or not translated.strip() or "\n" in translated or "\r" in translated:raise ValueError("无效译文")
    dst_lines[j]=translated+dst_lines[j][len(current_line):]
   except Exception as exc:
    had_error=True
    retry_errors.append({"cue":cue,"reason":str(exc)[:120]})
   sleep(MIN_INTERVAL)
  db[idx]="".join(dst_lines)
  if not had_error:resolved.append(cue)
 return {"translated_text":"".join(db),"resolved":resolved,"remaining":remaining+retry_errors,"attempted":len(selected)}
