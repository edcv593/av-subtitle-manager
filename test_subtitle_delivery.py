import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from subtitle_delivery import publish
from subtitle_files import subtitles_for

def srt(text):
 return ("1\n00:00:01,000 --> 00:00:03,000\n"+text+"\n\n"
         "2\n00:00:04,000 --> 00:00:06,000\n第二句中文字幕\n\n"
         "3\n00:00:07,000 --> 00:00:09,000\n第三句中文字幕\n").encode("utf-8")

class DeliveryTests(unittest.TestCase):
 def setUp(self):
  tmp=tempfile.TemporaryDirectory()
  self.addCleanup(tmp.cleanup)
  root=Path(tmp.name)
  self.media=root/"media";self.media.mkdir()
  self.archive=root/"data"/"subtitle_archives"
  self.video=self.media/"IPZZ-791.mp4";self.video.touch()
  self.zh=self.media/"IPZZ-791.zh.srt"
  self.ja=self.media/"IPZZ-791.ja.srt"
  self.zh.write_bytes(srt("原始中文字幕"))
  self.ja.write_bytes(srt("これは日本語です"))
 def test_publish_archives_all_and_leaves_one(self):
  expected={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in subtitles_for(self.video)}
  output=srt("优化后的中文字幕")
  target,folder,count=publish(self.video,output,"srt",self.archive,expected)
  self.assertEqual(count,2)
  self.assertEqual(subtitles_for(self.video),[target])
  self.assertEqual(target.read_bytes(),output)
  self.assertEqual((folder/self.zh.name).read_bytes(),srt("原始中文字幕"))
  self.assertEqual((folder/self.ja.name).read_bytes(),srt("これは日本語です"))
  self.assertEqual(len(json.loads((folder/"manifest.json").read_text())["files"]),2)
 def test_changed_original_never_cleaned(self):
  expected={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in subtitles_for(self.video)}
  self.zh.write_bytes(srt("用户刚刚手动修改"))
  with self.assertRaises(ValueError):
   publish(self.video,srt("优化版中文字幕"),"srt",self.archive,expected)
  self.assertTrue(self.ja.exists())
  self.assertIn("用户刚刚",self.zh.read_text())
 def test_invalid_output_does_not_touch_originals(self):
  with self.assertRaises(ValueError):
   publish(self.video,b"invalid","srt",self.archive)
  self.assertEqual(len(subtitles_for(self.video)),2)
 def test_archive_copy_failure_keeps_originals(self):
  with patch("subtitle_delivery.shutil.copy2",side_effect=OSError("archive unavailable")):
   with self.assertRaises(OSError):
    publish(self.video,srt("优化版中文字幕"),"srt",self.archive)
  self.assertEqual(len(subtitles_for(self.video)),2)
 def test_no_existing_subtitles_can_publish(self):
  self.zh.unlink();self.ja.unlink()
  target,folder,count=publish(self.video,srt("优化版中文字幕"),"srt",self.archive,expected={})
  self.assertEqual(count,0)
  self.assertEqual(subtitles_for(self.video),[target])

if __name__=="__main__":unittest.main()
