"""Safe sidecar audit and replacement helpers. Never read the video itself."""
from pathlib import Path
import time

SUB={".srt",".ass",".ssa",".vtt"}

def subtitles_for(video):
 stem=video.stem.casefold()
 return sorted((q for q in video.parent.iterdir() if q.is_file() and q.suffix.lower() in SUB and (q.stem.casefold()==stem or q.stem.casefold().startswith(stem+".") or q.stem.casefold().startswith(stem+"-"))),key=lambda q:q.name)

def choose_chinese(video):
 """Select only an unambiguous Chinese sidecar; never inspect video bytes."""
 import re
 import subtitle_compare
 files=subtitles_for(video)
 if not files:return None,"未找到外挂中文字幕"
 candidates=[]
 for path in files:
  try:
   if path.stat().st_size>4*1024*1024:continue
   raw=path.read_bytes()
   rows=subtitle_compare.entries(raw,path.suffix.lower().lstrip("."))
   if not rows:continue
   han=sum(bool(subtitle_compare.HAN.search(x["text"])) for x in rows)
   kana=sum(bool(subtitle_compare.JAPANESE.search(x["text"])) for x in rows)
   if han/max(1,len(rows))>=0.45 and kana/max(1,len(rows))<0.10:
    candidates.append(path)
  except (OSError,UnicodeError,ValueError):continue
 if not candidates:return None,"未找到可识别的中文字幕（可能只有日语字幕或字幕无法解析）"
 if len(candidates)==1:return candidates[0],""
 named=[p for p in candidates if re.search(r"(?:^|[.\\-_])(zh|chs|sc|chi|cn|简体|中文)(?:[.\\-_]|$)",p.stem,re.I)]
 if len(named)==1:return named[0],""
 return None,"存在多份可能的中文字幕，无法安全自动确定主字幕"

def replace_selected(video,selected,data,ext):
 """Back up exactly the selected sidecar and replace it in-place; preserve others."""
 if selected not in subtitles_for(video):raise ValueError("主字幕已改变，拒绝替换")
 if selected.suffix.lower()!="."+ext:raise ValueError("字幕格式不一致")
 backup=backup_path(selected)
 selected.rename(backup)
 try:
  with selected.open("xb") as f:f.write(data)
 except BaseException:
  if selected.exists():selected.unlink()
  backup.rename(selected)
  raise
 return selected,backup

def backups_for(video):
 stem=video.stem.casefold()
 return sorted((q for q in video.parent.iterdir() if q.is_file() and ".backup-" in q.name and q.name.casefold().startswith(stem) and q.name.rsplit(".backup-",1)[0].lower().endswith(tuple(SUB))),key=lambda q:q.name)

def backup_path(path):
 return path.with_name(path.name+".backup-"+str(time.time_ns()))

def replace(video,data,ext):
 """Backup the single current subtitle; restore on a failed write."""
 existing=subtitles_for(video)
 if len(existing)!=1:
  raise ValueError("安全替换要求恰好一份外挂字幕")
 old=existing[0]
 target=video.with_name(video.stem+".zh."+ext)
 if target!=old and target.exists():
  raise FileExistsError("目标字幕已存在")
 backup=backup_path(old)
 old.rename(backup)
 try:
  with target.open("xb") as f:f.write(data)
 except BaseException:
  if target.exists():target.unlink()
  backup.rename(old)
  raise
 return target,backup

def restore(video,backup_name):
 backups=[p for p in backups_for(video) if p.name==backup_name]
 if len(backups)!=1:raise ValueError("找不到指定备份")
 current=subtitles_for(video)
 if len(current)!=1:raise ValueError("安全恢复要求恰好一份当前字幕")
 backup=backups[0]
 original=backup.with_name(backup.name.rsplit(".backup-",1)[0])
 if original!=current[0] and original.exists():raise FileExistsError("原字幕文件名已被占用")
 displaced=backup_path(current[0])
 current[0].rename(displaced)
 try:backup.rename(original)
 except BaseException:
  displaced.rename(current[0])
  raise
 return original,displaced
