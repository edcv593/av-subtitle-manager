import unittest
from subtitle_quality import evaluate

def srt(texts):
 return ("\n\n".join(f"{i+1}\n00:00:{i:02d},000 --> 00:00:{i:02d},900\n{text}" for i,text in enumerate(texts))).encode()

class AVQualityTests(unittest.TestCase):
 def test_sparse_av_dialogue_not_penalized(self):
  q=evaluate(srt(["嗯","啊","你在干什么","好的"]), "srt")
  self.assertGreaterEqual(q["score"],85)
 def test_chinese_dialogue_passes(self):
  q=evaluate(srt(["今天你怎么来了","我想和你说几句话","等一下，我们慢慢说"]), "srt")
  self.assertEqual(q["level"],"recommended")
 def test_non_chinese_long_text_is_blocked(self):
  q=evaluate(srt(["This is an English sentence without Chinese text"]*5),"srt")
  self.assertEqual(q["level"],"blocked")
 def test_ad_spam_is_penalized(self):
  q=evaluate(srt(["扫码关注公众号获取更多内容"]*12),"srt")
  self.assertEqual(q["level"],"blocked")
 def test_invalid_timestamps_blocked(self):
  data=b"1\n00:00:05,000 --> 00:00:01,000\nHello\n"
  self.assertEqual(evaluate(data,"srt")["level"],"blocked")
 def test_empty_is_blocked(self):
  self.assertEqual(evaluate(b"","srt")["level"],"blocked")

if __name__=="__main__":unittest.main()
