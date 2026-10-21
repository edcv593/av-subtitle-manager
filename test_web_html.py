import ast,pathlib,unittest
class WebHTMLTests(unittest.TestCase):
 def test_javascript_tooltips_do_not_contain_raw_newlines(self):
  tree=ast.parse(pathlib.Path("app.py").read_text(encoding="utf-8"))
  html=next(node.value.value for node in tree.body if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=="HTML" for t in node.targets))
  self.assertIn('name.title=x.path+"\\n"+x.detail',html)
  self.assertIn('name.title=j.video_path+"\\n"+j.last_error',html)
  self.assertNotIn('name.title=x.path+"\n"+x.detail',html)
  self.assertNotIn('name.title=j.video_path+"\n"+j.last_error',html)
 def test_search_errors_are_readable(self):
  tree=ast.parse(pathlib.Path("app.py").read_text(encoding="utf-8"))
  html=next(node.value.value for node in tree.body if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=="HTML" for t in node.targets))
  self.assertIn("服务器返回非 JSON 响应",html)
  self.assertIn("HTTP "+chr(34)+"+r.status",html)
 def test_external_search_is_threaded(self):
  code=pathlib.Path("app.py").read_text(encoding="utf-8")
  self.assertIn("await asyncio.to_thread(external_providers.native_search",code)
 def test_translation_review_survives_scan_refresh(self):
  tree=ast.parse(pathlib.Path("app.py").read_text(encoding="utf-8"))
  html=next(node.value.value for node in tree.body if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=="HTML" for t in node.targets))
  self.assertIn('!document.getElementById("activeCandidateRow")',html)
  self.assertIn('subtitle_active_video',html)
  self.assertIn('subtitle_ref:',html)
  self.assertIn('"/api/subtitles/translate/retry-failed"',html)
  self.assertIn('重试翻译失败的条目',html)
  self.assertIn('连续 3 批没有翻译成功',html)
 def test_google_translation_progress_is_visible(self):
  tree=ast.parse(pathlib.Path("app.py").read_text(encoding="utf-8"))
  html=next(node.value.value for node in tree.body if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=="HTML" for t in node.targets))
  self.assertIn('el("progress")',html)
  self.assertIn('googleProgressUpdate(',html)
  self.assertIn('setInterval(()=>googleProgressUpdate(',html)
  self.assertIn('翻译中断：',html)
  self.assertIn('暂停（本批结束后）',html)
  self.assertIn('"/api/subtitles/translate/status"',html)
  self.assertIn('"/api/subtitles/translate/google"',html)
 def test_missing_subtitle_videos_can_open_review(self):
  tree=ast.parse(pathlib.Path("app.py").read_text(encoding="utf-8"))
  html=next(node.value.value for node in tree.body if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=="HTML" for t in node.targets))
  # The simplified library exposes one entry point for every indexed video.
  self.assertIn('let b=el("button","一键处理")',html)
  self.assertIn('b.onclick=()=>runWorkflow(x.path,tr,b)',html)
  self.assertIn('async function runWorkflow(path,tr,button)',html)
  self.assertIn('api("/api/workflow/plan","POST",{path})',html)
  self.assertIn('await show(path,tr)',html)
  # Review/upload tools still exist behind the unified entry point.
  self.assertIn('字幕审核',html)
  self.assertIn('/api/candidates/upload?',html)
  self.assertNotIn('["missing","review","error","no_code","downloaded","existing","skipped_c"].includes(x.status)',html)
if __name__=="__main__":unittest.main()
