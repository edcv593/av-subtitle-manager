"""Publish exactly one optimized subtitle next to a video.

Intermediate sidecars are archived under /data (outside the media directory).
Only subtitle files belonging to this video are considered; never read media bytes.
"""
import hashlib
import json
import os
import shutil
import tempfile
import time
from pathlib import Path

import subtitle_files
import subtitle_quality
import timeline

def _digest(path):
 h=hashlib.sha256()
 with path.open("rb") as stream:
  for block in iter(lambda:stream.read(1024*1024),b""):h.update(block)
 return h.hexdigest()

def publish(video,output,ext,archive_root,expected=None):
 """Safely publish one subtitle and archive every old sidecar.

 Returns (target, archive_directory, removed_count). Fail closed if the
 media changes during preparation. Archives are retained for recovery.
 """
 video=Path(video)
 archive_root=Path(archive_root)
 if ext not in ("srt","ass","ssa","vtt"):raise ValueError("不支持的字幕格式")
 if not video.is_file():raise ValueError("影片不存在")
 if not isinstance(output,bytes) or len(output)>4*1024*1024:raise ValueError("优化字幕无效或过大")
 if not timeline.cues(output,ext) or subtitle_quality.evaluate(output,ext)["level"]=="blocked":
  raise ValueError("优化版字幕没有通过时间轴或质量校验")
 old=subtitle_files.subtitles_for(video)
 if expected is not None:
  expected={str(Path(p)):sha for p,sha in expected.items()}
  if {str(p):_digest(p) for p in old}!=expected:
   raise ValueError("处理期间字幕发生变化，停止清理")
 target=video.with_name(video.stem+".zh."+ext)
 # An untracked target is never overwritten.
 if target.exists() and target not in old:raise FileExistsError("目标字幕已被占用")
 key=hashlib.sha256(str(video.resolve()).encode("utf-8")).hexdigest()[:20]
 stamp=str(time.time_ns())
 archive=archive_root/key/stamp
 archive.mkdir(parents=True,exist_ok=False)
 staged=None
 written=False
 try:
  metadata=[]
  for p in old:
   sha=_digest(p)
   dest=archive/p.name
   shutil.copy2(p,dest)
   if _digest(dest)!=sha:raise OSError("原始字幕备份校验失败")
   metadata.append({"name":p.name,"sha256":sha})
  (archive/"manifest.json").write_text(json.dumps({"video":str(video),"files":metadata},ensure_ascii=False,indent=2),encoding="utf-8")
  fd,tmp=tempfile.mkstemp(prefix="."+video.stem+".optimized-",suffix="."+ext,dir=video.parent)
  staged=Path(tmp)
  with os.fdopen(fd,"wb") as stream:
   stream.write(output);stream.flush();os.fsync(stream.fileno())
  if hashlib.sha256(output).hexdigest()!=_digest(staged):raise OSError("优化字幕写入校验失败")
  if expected is not None and {str(p):_digest(p) for p in subtitle_files.subtitles_for(video)}!=expected:
   raise ValueError("发布前字幕发生变化")
  os.replace(staged,target);staged=None;written=True
  # Do not delete anything unless all original files were archived and
  # the new output is verified.
  if _digest(target)!=hashlib.sha256(output).hexdigest():raise OSError("最终字幕校验失败")
  for p in old:
   if p!=target and p.exists():p.unlink()
  remaining=subtitle_files.subtitles_for(video)
  if remaining!=[target]:raise OSError("媒体目录仍有其他字幕，检查清理权限")
  return target,archive,len(old)
 except BaseException:
  if staged is not None and staged.exists():staged.unlink()
  # Original copies remain safely in the archive even on partial cleanup.
  # If a new output was written but cleanup failed, never silently delete
  # that output: the user can recover originals from the manifest.
  raise
