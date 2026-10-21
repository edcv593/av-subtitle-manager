import unittest
from subtitle_optimizer import reference_excerpt
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

class ReferenceSubtitleTests(unittest.TestCase):
 def test_srt_reference_excerpt(self):
  raw=b"1\n00:00:01,000 --> 00:00:02,000\nHello\n"
  self.assertIn("Hello",reference_excerpt(raw,"srt"))
 def test_reference_matches_chinese_time_window(self):
  chinese=b"1\n00:00:01,000 --> 00:00:02,000\nChinese\n"
  japanese=(b"1\n00:00:01,200 --> 00:00:02,100\nJapanese near\n\n"
            b"2\n01:00:00,000 --> 01:00:02,000\nJapanese far\n")
  excerpt=opt.reference_for_window(chinese,"srt",japanese,"srt")
  self.assertIn("Japanese near",excerpt)
  self.assertNotIn("Japanese far",excerpt)
 def test_reference_rejects_invalid_timeline(self):
  with self.assertRaises(ValueError):
   opt.reference_for_window(SRT,"srt",b"not a subtitle","srt")
 def test_ai_batch_complete_lines(self):
  raw=("1\n00:00:01,000 --> 00:00:02,000\n中文第一句\n\n2\n00:00:03,000 --> 00:00:04,000\n中文第二句\n").encode()
  first,nxt,done=opt.ai_batch(raw,0,55)
  self.assertFalse(done)
  second,last,done=opt.ai_batch(raw,nxt,55)
  self.assertTrue(done)
  self.assertEqual(first+second,raw.decode())
  self.assertEqual(last,len(raw.decode()))
 def test_ai_suggestions_rejects_ambiguous_duplicate_line(self):
  import json
  raw=("1\n00:00:01,000 --> 00:00:02,000\n重复台词\n\n2\n00:00:03,000 --> 00:00:04,000\n重复台词\n").encode()
  response={"choices":[{"message":{"content":json.dumps({"suggestions":[{"before":"重复台词","after":"新台词"}]})}}]}
  class FakeResponse:
   def __enter__(self):return self
   def __exit__(self,*args):return False
   def read(self,n):return json.dumps(response).encode()
  with patch.object(opt.urllib.request,"urlopen",return_value=FakeResponse()):
   self.assertEqual(opt.ai_suggestions(raw,"srt","test-key"),[])
 def test_ai_batch_rejects_midline_offset(self):
  with self.assertRaises(ValueError):opt.ai_batch(SRT,2)
 def test_second_batch_reference_uses_later_cues(self):
  chinese=("1\n00:00:01,000 --> 00:00:02,000\n中文一\n\n2\n00:00:10,000 --> 00:00:11,000\n中文二\n").encode()
  japanese=("1\n00:00:01,000 --> 00:00:02,000\n日本語一\n\n2\n00:00:10,000 --> 00:00:11,000\n日本語二\n").encode()
  _,offset,_=opt.ai_batch(chinese,0,40)
  result=opt.reference_for_window(chinese,"srt",japanese,"srt",offset=offset)
  self.assertIn("日本語二",result)
  self.assertNotIn("日本語一",result)
 def test_utf16_reference_text(self):
  raw="1\n00:00:01,000 --> 00:00:02,000\nこんにちは\n".encode("utf-16")
  self.assertIn("こんにちは",reference_excerpt(raw,"srt"))
  self.assertIn("こんにちは",opt.reference_for_window(SRT,"srt",raw,"srt"))
 def test_gb18030_reference_text(self):
  raw="1\n00:00:01,000 --> 00:00:02,000\n原语言参考\n".encode("gb18030")
  self.assertIn("原语言参考",reference_excerpt(raw,"srt"))
 def test_ass_reference_custom_format(self):
  raw=("[Script Info]\nTitle: Japanese\n[Events]\n"
       "Format: Layer, End, Start, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
       "Dialogue: 0,0:00:02.00,0:00:01.00,Default,,0,0,0,,近い\n"
       "Dialogue: 0,0:20:02.00,0:20:01.00,Default,,0,0,0,,遠い\n").encode()
  excerpt=opt.reference_for_window(SRT,"srt",raw,"ass")
  self.assertIn("近い",excerpt)
  self.assertNotIn("遠い",excerpt)
 def test_reject_invalid_reference(self):
  with self.assertRaises(ValueError):reference_excerpt(b"hello","srt")

if __name__=="__main__":unittest.main()
