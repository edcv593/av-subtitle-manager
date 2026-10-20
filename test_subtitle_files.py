import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from subtitle_files import subtitles_for,backups_for,replace,restore

class SubtitleFileTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory()
  self.addCleanup(self.tmp.cleanup)
  self.video=Path(self.tmp.name)/"IPX-123.mp4"
  self.video.touch()
  self.old=Path(self.tmp.name)/"IPX-123.zh.srt"
  self.old.write_bytes(b"old subtitle")
 def test_replace_and_restore(self):
  target,backup=replace(self.video,b"new subtitle","srt")
  self.assertEqual(target.read_bytes(),b"new subtitle")
  self.assertEqual(backup.read_bytes(),b"old subtitle")
  self.assertEqual(len(backups_for(self.video)),1)
  restored,displaced=restore(self.video,backup.name)
  self.assertEqual(restored.read_bytes(),b"old subtitle")
  self.assertEqual(displaced.read_bytes(),b"new subtitle")
 def test_refuse_multiple_sidecars(self):
  (self.video.parent/"IPX-123.ass").write_text("other")
  with self.assertRaises(ValueError):replace(self.video,b"new","srt")
  self.assertEqual(self.old.read_bytes(),b"old subtitle")
 def test_no_existing_subtitle(self):
  self.old.unlink()
  with self.assertRaises(ValueError):replace(self.video,b"new","srt")
 def test_restore_requires_exact_backup_name(self):
  with self.assertRaises(ValueError):restore(self.video,"../IPX-123.zh.srt")
 def test_write_failure_restores_original(self):
  with patch("pathlib.Path.open",side_effect=OSError("simulated write failure")):
   with self.assertRaises(OSError):replace(self.video,b"new","srt")
  self.assertEqual(self.old.read_bytes(),b"old subtitle")
  self.assertEqual(len(backups_for(self.video)),0)

if __name__=="__main__":unittest.main()
