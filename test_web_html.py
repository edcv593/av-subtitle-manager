import ast,pathlib,unittest
class WebHTMLTests(unittest.TestCase):
 def test_javascript_tooltips_do_not_contain_raw_newlines(self):
  tree=ast.parse(pathlib.Path("app.py").read_text(encoding="utf-8"))
  html=next(node.value.value for node in tree.body if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=="HTML" for t in node.targets))
  self.assertIn('name.title=x.path+"\\n"+x.detail',html)
  self.assertIn('name.title=j.video_path+"\\n"+j.last_error',html)
  self.assertNotIn('name.title=x.path+"\n"+x.detail',html)
  self.assertNotIn('name.title=j.video_path+"\n"+j.last_error',html)
 def test_missing_subtitle_videos_can_open_review(self):
  tree=ast.parse(pathlib.Path("app.py").read_text(encoding="utf-8"))
  html=next(node.value.value for node in tree.body if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=="HTML" for t in node.targets))
  self.assertIn('["missing","review","error","no_code","downloaded","existing","skipped_c"].includes(x.status)',html)
  self.assertIn('字幕审核',html)
  self.assertIn('/api/candidates/upload?',html)
if __name__=="__main__":unittest.main()
