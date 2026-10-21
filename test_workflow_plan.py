import unittest
from workflow_plan import plan

class WorkflowPlanTests(unittest.TestCase):
 def test_chinese_still_starts_with_japanese_reference(self):
  p=plan("/media/IPZZ-791.mkv",["IPZZ-791.zh.srt"],"IPZZ-791","existing")
  self.assertEqual(p["action"],"pipeline")
  self.assertEqual(p["steps"][0]["id"],"japanese")
  self.assertEqual(p["steps"][1]["id"],"chinese")
  self.assertFalse(p["requires_confirmation"])
 def test_japanese_only_still_searches_chinese(self):
  p=plan("/media/IPZZ-791.mkv",["IPZZ-791.ja.srt"],"IPZZ-791","missing")
  self.assertEqual(p["action"],"pipeline")
  self.assertEqual(p["steps"][0]["status"],"ready")
  self.assertEqual(p["steps"][1]["status"],"pending")
 def test_unknown_sidecar_does_not_block_pipeline(self):
  p=plan("/media/IPZZ-791.mkv",["IPZZ-791.srt"],"IPZZ-791","existing")
  self.assertEqual(p["action"],"pipeline")
 def test_candidate_still_runs_japanese_first(self):
  self.assertEqual(plan("/media/IPZZ-791.mkv",[],"IPZZ-791","missing",2)["steps"][0]["id"],"japanese")
 def test_final_step_is_archive(self):
  p=plan("/media/IPZZ-791.mkv",[],"IPZZ-791","missing")
  self.assertEqual([step["id"] for step in p["steps"]],["japanese","chinese","compare","publish","archive"])
  self.assertEqual(p["output"],"IPZZ-791.zh.srt")
 def test_skip_c(self):
  self.assertEqual(plan("/media/IPZZ-791-C.mkv",[],"IPZZ-791","skipped_c")["action"],"blocked")
 def test_unknown_code(self):
  self.assertEqual(plan("/media/unknown.mkv",[],None,"missing")["action"],"no_code")

if __name__=="__main__":unittest.main()
