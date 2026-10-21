import unittest
from unittest.mock import patch
import json
import subtitle_compare as sc

MAIN=("1\n00:00:01,000 --> 00:00:03,000\n你为什么那么做？\n\n"
      "2\n00:00:05,000 --> 00:00:07,000\n这件事很好。\n").encode()
JA=("1\n00:00:01,000 --> 00:00:03,000\nどうしてそんなことをしたの？\n\n"
    "2\n00:00:20,000 --> 00:00:22,000\nわかりました\n").encode()
ZH=("1\n00:00:01,100 --> 00:00:02,900\n你干嘛这么做？\n\n").encode()

class CompareTests(unittest.TestCase):
 def test_multi_reference_overlap_excludes_unmatched(self):
  report=sc.review_batch(MAIN,"srt",[("ja",JA,"srt",0),("zh-alt",ZH,"srt",0)])
  self.assertEqual(len(report["rows"][0]["references"]),2)
  self.assertEqual(report["rows"][1]["references"],[])
  self.assertTrue(report["done"])
 def test_shift_and_no_guess(self):
  late=("1\n00:00:04,000 --> 00:00:06,000\nなぜ？\n").encode()
  self.assertEqual(sc.review_batch(MAIN,"srt",[("ja",late,"srt",0)])["rows"][0]["references"],[])
  self.assertEqual(len(sc.review_batch(MAIN,"srt",[("ja",late,"srt",-3)])["rows"][0]["references"]),1)
 def test_offset_and_missing_references(self):
  r=sc.review_batch(MAIN,"srt",[],offset=1)
  self.assertEqual(r["rows"][0]["index"],1)
  with self.assertRaises(ValueError):sc.review_batch(MAIN,"srt",[],offset=-1)
 def test_ai_rejects_unmatched_and_duplicate_original(self):
  rows=sc.review_batch(MAIN,"srt",[("ja",JA,"srt",0)])["rows"]
  response={"choices":[{"message":{"content":json.dumps({"suggestions":[
   {"index":0,"before":"你为什么那么做？","after":"你干嘛那么做？","reason":"口语更自然"},
   {"index":1,"before":"这件事很好。","after":"很好","reason":"不可靠"}
  ]},ensure_ascii=False)}}]}
  class FakeResponse:
   def __enter__(self):return self
   def __exit__(self,*args):return False
   def read(self,n):return json.dumps(response).encode()
  with patch.object(sc.urllib.request,"urlopen",return_value=FakeResponse()):
   out=sc.ai_review(rows,"key","deepseek-chat","https://api.deepseek.com/chat/completions",MAIN.decode().splitlines())
  self.assertEqual(len(out),1)
  self.assertEqual(out[0]["before"],"你为什么那么做？")
 def test_reject_duplicate_text_changes(self):
  rows=sc.review_batch(MAIN,"srt",[("ja",JA,"srt",0)])["rows"]
  response={"choices":[{"message":{"content":json.dumps({"suggestions":[{"index":0,"before":"你为什么那么做？","after":"你怎么这样？","reason":"测试"}]},ensure_ascii=False)}}]}
  class FakeResponse:
   def __enter__(self):return self
   def __exit__(self,*args):return False
   def read(self,n):return json.dumps(response).encode()
  with patch.object(sc.urllib.request,"urlopen",return_value=FakeResponse()):
   out=sc.ai_review(rows,"key","deepseek-chat","https://api.deepseek.com/chat/completions",["你为什么那么做？","你为什么那么做？"])
  self.assertEqual(out,[])

if __name__=="__main__":unittest.main()
