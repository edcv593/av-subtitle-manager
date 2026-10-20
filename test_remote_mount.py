import ast,pathlib,tempfile,unittest
class RemoteMountTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  tree=ast.parse(pathlib.Path("app.py").read_text(encoding="utf-8"))
  cls.source=pathlib.Path("app.py").read_text(encoding="utf-8")
  fn=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=="sidecar")
  module=ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[]))
  namespace={"Path":pathlib.Path,"SUB":{".srt",".ass",".ssa",".vtt"}}
  exec(compile(module,"app.py","exec"),namespace)
  cls.sidecar=staticmethod(namespace["sidecar"])
 def test_directory_cache(self):
  p=pathlib.Path("/media/IPX-123.mp4")
  self.assertTrue(self.sidecar(p,["IPX-123.zh.srt","IPX-123.mp4"]))
  self.assertFalse(self.sidecar(p,["IPX-124.zh.srt","IPX-123.mp4"]))
  self.assertTrue(self.sidecar(p,["IPX-123.zh.ass"]))
 def test_remote_mode_never_probes_video_duration_for_download(self):
  self.assertIn('None if REMOTE_MOUNT_MODE else video_duration(p)',self.source)
  self.assertIn('process(c,p,directory_names=files if REMOTE_MOUNT_MODE else None)',self.source)
 def test_default_is_opt_in(self):
  self.assertIn('os.getenv("REMOTE_MOUNT_MODE","false")',self.source)
if __name__=="__main__":unittest.main()
