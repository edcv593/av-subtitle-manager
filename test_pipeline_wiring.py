"""Guard against reverting to the old manual-first proofreading workflow."""
import ast
import pathlib
import unittest

class PipelineWiringTests(unittest.TestCase):
 def test_worker_order_and_finalizer(self):
  code=pathlib.Path("app.py").read_text(encoding="utf-8")
  tree=ast.parse(code)
  worker=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=="review_worker_one")
  body=ast.get_source_segment(code,worker)
  self.assertLess(body.index("reference_id=review_auto_reference(p)"),body.index("base=review_best_chinese("))
  self.assertLess(body.index("base=review_best_chinese("),body.index("subtitle_compare.ai_review("))
  self.assertLess(body.index("subtitle_compare.ai_review("),body.index("subtitle_delivery.publish("))
  self.assertNotIn("subtitle_files.replace_selected(",body)
  self.assertIn('DATA/"subtitle_archives"',body)
 def test_docker_packages_all_pipeline_modules(self):
  docker=pathlib.Path("Dockerfile").read_text(encoding="utf-8")
  self.assertIn("subtitle_sources.py",docker)
  self.assertIn("subtitle_delivery.py",docker)
 def test_queue_defaults_to_automatic_output(self):
  code=pathlib.Path("app.py").read_text(encoding="utf-8")
  self.assertIn('auto.type="checkbox";auto.checked=true;',code)
  self.assertIn("自动生成最终优化字幕",code)

if __name__=="__main__":unittest.main()
