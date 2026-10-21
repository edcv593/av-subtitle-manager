import unittest
from subtitle_sources import choose,evaluate_chinese

def sub(lines,shift=0):
 return "".join(f"{i}\n00:00:{i*3+shift:02d},000 --> 00:00:{i*3+shift+2:02d},000\n{line}\n\n" for i,line in enumerate(lines,1)).encode()

class SourceRankingTests(unittest.TestCase):
 def setUp(self):
  self.ja=sub(["これは日本語です","大丈夫ですか","今日はいい天気です"])
  self.zh=sub(["这是第一句中文字幕","这是第二句中文字幕","这是第三句中文字幕"])
 def test_chinese_base_is_accepted(self):
  self.assertIsNotNone(evaluate_chinese(self.zh,"srt",self.ja,"srt"))
 def test_japanese_only_rejected(self):
  self.assertIsNone(evaluate_chinese(self.ja,"srt",self.ja,"srt"))
 def test_unaligned_chinese_not_chosen(self):
  late=sub(["这是第一句中文字幕","这是第二句中文字幕","这是第三句中文字幕"],30)
  result=choose([{"name":"late","data":late,"ext":"srt","source":"local"},
                 {"name":"good","data":self.zh,"ext":"srt","source":"web"}],self.ja,"srt")
  self.assertEqual(result["name"],"good")
  self.assertEqual(result["matched"],3)
 def test_duplicate_payloads_are_ignored(self):
  candidates=[{"name":"first","data":self.zh,"ext":"srt","source":"local"},
              {"name":"second","data":self.zh,"ext":"srt","source":"web"}]
  self.assertEqual(choose(candidates,self.ja,"srt")["name"],"first")

if __name__=="__main__":unittest.main()
