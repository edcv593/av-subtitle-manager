"""Non-destructive NAS subtitle workflow planning.

Plan work without reading video/audio bytes, changing subtitle sidecars or
silently triggering external translation. All existing APIs remain available.
"""
from pathlib import Path

def plan(video,subtitle_names,code=None,status=None,candidates=0):
 names=[Path(name).name for name in subtitle_names]
 chinese=[name for name in names if name.lower().endswith((".zh.srt",".zh.ass",".zh.ssa",".zh.vtt",".chs.srt",".cht.srt",".zh-cn.srt",".zh-tw.srt"))]
 japanese=[name for name in names if name.lower().endswith((".ja.srt",".ja.ass",".ja.ssa",".ja.vtt",".jp.srt"))]
 data={"video":Path(video).name,"existing":names,"chinese":chinese,"japanese":japanese,"candidates":candidates,
       "steps":[],"action":None,"requires_confirmation":True}
 if status=="skipped_c" or Path(video).stem.upper().endswith("-C"):
  data.update(action="blocked",steps=[{"id":"blocked","title":"跳过 -C 影片","status":"blocked"}])
 elif chinese:
  data.update(action="review",steps=[{"id":"inspect","title":"核查已有中文字幕","status":"ready"},{"id":"review","title":"按需预览和优化","status":"manual"}])
 elif japanese:
  data.update(action="translate",steps=[{"id":"reference","title":"使用已有日语字幕","status":"ready"},{"id":"translate","title":"Google 初译与 AI 校对","status":"manual"},{"id":"save","title":"预览并确认保存","status":"manual"}])
 elif candidates:
  data.update(action="review",steps=[{"id":"candidates","title":"审查已下载候选字幕","status":"ready"},{"id":"save","title":"确认后保存","status":"manual"}])
 elif not code:
  data.update(action="no_code",steps=[{"id":"identify","title":"无法识别番号，等待人工处理","status":"blocked"}])
 else:
  data.update(action="search",steps=[{"id":"search","title":"检索字幕来源","status":"ready"},{"id":"review","title":"检查搜索候选","status":"pending"},{"id":"translate","title":"没有中文时尝试日语翻译","status":"pending"},{"id":"save","title":"预览并确认保存","status":"manual"}])
 return data
