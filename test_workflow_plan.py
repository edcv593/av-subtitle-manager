import unittest
from workflow_plan import plan

class WorkflowPlanTests(unittest.TestCase):
 def test_chinese_prefers_review_without_search(self):
  p=plan("/media/IPZZ-791.mkv",["IPZZ-791.zh.srt"],"IPZZ-791","existing")
  self.assertEqual(p["action"],"review")
 def test_japanese_requires_explicit_translate(self):
  p=plan("/media/IPZZ-791.mkv",["IPZZ-791.ja.srt"],"IPZZ-791","missing")
  self.assertEqual(p["action"],"translate")
  self.assertTrue(p["requires_confirmation"])
 def test_unknown_language_sidecar_does_not_trigger_search(self):
  result=plan("/media/IPZZ-791.mkv",["IPZZ-791.srt"],"IPZZ-791","existing")
  self.assertEqual(result["action"],"review")
 def test_candidate_prefers_review(self):
  self.assertEqual(plan("/media/IPZZ-791.mkv",[],"IPZZ-791","missing",2)["action"],"review")
 def test_missing_search_does_not_write(self):
  self.assertEqual(plan("/media/IPZZ-791.mkv",[],"IPZZ-791","missing")["action"],"search")
 def test_skip_c(self):
  self.assertEqual(plan("/media/IPZZ-791-C.mkv",[],"IPZZ-791","skipped_c")["action"],"blocked")
 def test_unknown_code(self):
  self.assertEqual(plan("/media/unknown.mkv",[],None,"missing")["action"],"no_code")

if __name__=="__main__":unittest.main()
