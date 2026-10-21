import unittest
from unittest.mock import patch
import json
import urllib.error
import subtitle_google as g
import timeline

SRT=("1\n00:00:01,000 --> 00:00:02,000\nこんにちは\n\n"
     "2\n00:00:03,000 --> 00:00:04,000\nありがとう\n").encode()

class GoogleSubtitleTests(unittest.TestCase):
 def test_translation_preserves_timeline_and_is_resumable(self):
  def translator(t):return {"こんにちは":"你好","ありがとう":"谢谢"}[t]
  first=g.translate_srt(SRT,0,1,translator,sleep=lambda n:None)
  self.assertFalse(first["done"])
  self.assertEqual(first["next_offset"],1)
  second=g.translate_srt(first["translated_text"].encode(),1,1,translator,sleep=lambda n:None)
  self.assertTrue(second["done"])
  self.assertEqual(timeline.cues(SRT,"srt"),timeline.cues(second["translated_text"].encode(),"srt"))
  self.assertIn("你好",second["translated_text"])
  self.assertIn("谢谢",second["translated_text"])
 def test_failure_keeps_original_japanese(self):
  def fail(t):raise ValueError("429 Too Many Requests")
  result=g.translate_srt(SRT,0,1,fail,sleep=lambda n:None)
  self.assertIn("こんにちは",result["translated_text"])
  self.assertEqual(len(result["failed"]),1)
 def test_invalid_offset(self):
  with self.assertRaises(ValueError):g.translate_srt(SRT,-1,1,sleep=lambda n:None)
 def test_google_response_parser(self):
  class Response:
   def __enter__(self):return self
   def __exit__(self,*args):return False
   def read(self,n):return json.dumps([[["你好","こんにちは",None,None]]]).encode()
  self.assertEqual(g.google_translate("こんにちは",opener=lambda *args,**kwargs:Response(),sleep=lambda n:None),"你好")
 def test_google_failure_retry_bounded(self):
  calls=[]
  def opener(*args,**kwargs):
   calls.append(1)
   raise urllib.error.HTTPError("https://translate.googleapis.com",429,"Too Many Requests",None,None)
  with self.assertRaises(ValueError):g.google_translate("こんにちは",opener=opener,sleep=lambda n:None,retries=2)
  self.assertEqual(len(calls),3)

if __name__=="__main__":unittest.main()
