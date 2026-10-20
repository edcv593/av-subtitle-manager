"""Conservative subtitle timeline checks; never infer spoken-content alignment."""
import re,subprocess
def video_duration(path):
 try:
  p=subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","default=noprint_wrappers=1:nokey=1",str(path)],capture_output=True,text=True,timeout=35,check=True)
  seconds=float(p.stdout.strip())
  return seconds if 0<seconds<86400 else None
 except (OSError,ValueError,subprocess.SubprocessError):return None
def stamp(s):
 m=re.fullmatch(r"(?:(\d{1,2}):)?(\d{1,2}):(\d{2})[,.](\d{1,3})",s.strip())
 if not m:return None
 h,minute,sec,ms=m.groups();h=int(h or 0);minute=int(minute);sec=int(sec)
 if minute>=60 or sec>=60:return None
 return h*3600+minute*60+sec+int(ms.ljust(3,"0"))/1000
def decode(data):
 for enc in ("utf-8-sig","utf-16","gb18030"):
  try:return data.decode(enc)
  except UnicodeError:pass
 return None
def cues(data,ext):
 text=decode(data)
 if not text:return None
 out=[]
 if ext in ("srt","vtt"):
  for line in text.splitlines():
   if "-->" not in line:continue
   parts=line.split("-->",1)
   a=stamp(parts[0]);b=stamp(parts[1].strip().split()[0])
   if a is None or b is None:return None
   out.append((a,b))
 elif ext in ("ass","ssa"):
  if "[Events]" not in text:return None
  in_events=False;start_idx=1;end_idx=2
  for line in text.splitlines():
   s=line.strip()
   if s.startswith("["):in_events=s.lower()=="[events]";continue
   if not in_events:continue
   if s.lower().startswith("format:"):
    fields=[v.strip().lower() for v in s.split(":",1)[1].split(",")]
    if "start" not in fields or "end" not in fields:return None
    start_idx=fields.index("start");end_idx=fields.index("end")
   if s.lower().startswith("dialogue:"):
    fields=s.split(":",1)[1].split(",",max(start_idx,end_idx)+1)
    if len(fields)<=max(start_idx,end_idx):return None
    a=stamp(fields[start_idx]);b=stamp(fields[end_idx])
    if a is None or b is None:return None
    out.append((a,b))
 else:return None
 return out if out else None
def assess(data,ext,duration):
 timeline=cues(data,ext)
 if not timeline:return {"ok":False,"reason":"无法解析字幕时间轴","cues":0}
 if duration is None:return {"ok":False,"reason":"无法获取视频时长，需人工审核","cues":len(timeline)}
 if len(timeline)<3:return {"ok":False,"reason":"字幕事件少于3条，需人工审核","cues":len(timeline)}
 for a,b in timeline:
  if a<0 or b<=a:return {"ok":False,"reason":"字幕时间戳无效","cues":len(timeline)}
  if b-a>900:return {"ok":False,"reason":"字幕单条跨度异常","cues":len(timeline)}
 last=max(b for _,b in timeline)
 if last>duration+min(15,duration*.02):
  return {"ok":False,"reason":f"字幕结束于{last:.0f}秒，超出视频时长{duration:.0f}秒","cues":len(timeline)}
 # Sparse/partial subtitles are legitimate; do not reject solely for early ending.
 # Detect severe non-monotonic ordering, not normal overlapping dialogue.
 inversions=sum(1 for i in range(1,len(timeline)) if timeline[i][0]+3<timeline[i-1][0])
 if inversions>max(2,len(timeline)*.02):
  return {"ok":False,"reason":"字幕事件顺序明显异常","cues":len(timeline)}
 return {"ok":True,"reason":f"时间轴基本合理：{len(timeline)}条，结束{last:.0f}秒/视频{duration:.0f}秒；不保证内容同步","cues":len(timeline)}
