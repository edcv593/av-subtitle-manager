"""NAS automated subtitle workflow plan, without accessing media bytes."""
from pathlib import Path

STAGES=(
 ("japanese","检索并验证日语原生字幕"),
 ("chinese","下载并评选最佳中文字幕"),
 ("compare","按时间轴对照并用 AI 优化"),
 ("publish","生成唯一优化版字幕"),
 ("archive","归档原字幕与中间资料"),
)

def plan(video,subtitle_names,code=None,status=None,candidates=0):
 names=[Path(name).name for name in subtitle_names]
 chinese=[name for name in names if name.lower().endswith((".zh.srt",".zh.ass",".zh.ssa",".zh.vtt",".chs.srt",".cht.srt",".zh-cn.srt",".zh-tw.srt"))]
 japanese=[name for name in names if name.lower().endswith((".ja.srt",".ja.ass",".ja.ssa",".ja.vtt",".jp.srt"))]
 data={"video":Path(video).name,"existing":names,"chinese":chinese,"japanese":japanese,"candidates":candidates,
       "steps":[],"action":None,"requires_confirmation":False,"output":Path(video).stem+".zh.srt"}
 if status=="skipped_c" or Path(video).stem.upper().endswith("-C"):
  data.update(action="blocked",steps=[{"id":"blocked","title":"跳过 -C 影片","status":"blocked"}])
 elif not code:
  data.update(action="no_code",steps=[{"id":"identify","title":"无法识别番号，等待人工处理","status":"blocked"}])
 else:
  data.update(action="pipeline",steps=[
   {"id":stage,"title":title,"status":"ready" if stage=="japanese" and japanese else "pending"}
   for stage,title in STAGES])
 return data
