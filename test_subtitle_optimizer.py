import unittest
from unittest.mock import patch
import subtitle_optimizer as opt

SRT=("1\n00:00:01,000 --> 00:00:02,000\n這裡　很好！！\n\n2\n00:00:03,000 --> 00:00:04,000\n你好\n").encode()
ASS=("[Script Info]\nTitle: Test\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\nDialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,這裡！！\n").encode()

class OptimizerTests(unittest.TestCase):
 def test_srt_timing_preserved(self):
  with patch.object(opt,"converter",return_value=type("Converter",(),{"convert":lambda self,s:s.replace("這裡","这里")})()):
   new,changes=opt.optimize(SRT,"srt")
  self.assertIn(b"00:00:01,000 --> 00:00:02,000",new)
  self.assertIn("这里很好！".encode(),new)
  self.assertEqual(len(changes),1)
 def test_ass_header_and_timing_preserved(self):
  with patch.object(opt,"converter",return_value=type("Converter",(),{"convert":lambda self,s:s.replace("這裡","这里")})()):
   new,changes=opt.optimize(ASS,"ass")
  self.assertIn(b"0:00:01.00,0:00:02.00",new)
  self.assertIn("这里！".encode(),new)
  self.assertEqual(len(changes),1)
 def test_preview_digest(self):
  report=opt.preview(SRT,"srt",simplify=False)
  self.assertEqual(len(report["original_sha256"]),64)
  self.assertTrue(report["changed"])
 def test_reject_newlines_in_replacements(self):
  with self.assertRaises(ValueError):
   opt.optimize(SRT,"srt",False,False,{"你好":"wrong\n00:00:00,000 --> 00:00:00,100"})
 def test_unchanged_bytes(self):
  new,changes=opt.optimize(SRT,"srt",False,False)
  self.assertEqual(new,SRT)
  self.assertEqual(changes,[])

if __name__=="__main__":unittest.main()
