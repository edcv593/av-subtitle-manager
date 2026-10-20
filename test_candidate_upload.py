import ast
import hashlib
import io
import pathlib
import tempfile
import unittest
import zipfile

# Extract the pure upload helpers without importing FastAPI (CI installs no runtime deps).
tree = ast.parse(pathlib.Path("app.py").read_text(encoding="utf-8"))
functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in ("extract_uploaded_subtitle", "candidate_payload")]
namespace = {"Path": pathlib.Path, "SUB": {".srt", ".ass", ".ssa", ".vtt"}, "LIMIT": 1024 * 1024, "zipfile": zipfile, "io": io, "hashlib": hashlib, "re": __import__("re")}
exec(compile(ast.Module(body=functions, type_ignores=[]), "app.py", "exec"), namespace)
extract = namespace["extract_uploaded_subtitle"]
load = namespace["candidate_payload"]

def zipped(entries):
 stream = io.BytesIO()
 with zipfile.ZipFile(stream, "w") as archive:
  for name, data in entries:
   archive.writestr(name, data)
 return stream.getvalue()

class UploadTests(unittest.TestCase):
 def test_single_srt_in_zip(self):
  payload = b"1\n00:00:00,000 --> 00:00:01,000\nHello\n"
  data, ext = extract(zipped([("folder/SSIS-334.srt", payload), ("README.txt", b"info")]), "subs.zip", "SSIS-334")
  self.assertEqual((data, ext), (payload, "srt"))

 def test_multiple_subtitles_rejected(self):
  with self.assertRaisesRegex(ValueError, "恰好"):
   extract(zipped([("a.srt", b"a"), ("b.ass", b"b")]), "subs.zip", "SSIS-334")

 def test_invalid_zip_rejected(self):
  with self.assertRaises(ValueError):
   extract(b"not zip", "subs.zip", "SSIS-334")

 def test_oversize_zip_member_rejected(self):
  with self.assertRaisesRegex(ValueError, "过大"):
   extract(zipped([("a.srt", b"a" * (namespace["LIMIT"] + 1))]), "subs.zip", "SSIS-334")

 def test_local_candidate_roundtrip_and_tamper_detection(self):
  payload = b"example subtitle"
  digest = hashlib.sha256(payload).hexdigest()
  with tempfile.TemporaryDirectory() as folder:
   namespace["DATA"] = pathlib.Path(folder)
   cache = pathlib.Path(folder) / "candidate_uploads"
   cache.mkdir()
   (cache / digest).write_bytes(payload)
   self.assertEqual(load("local-subtitle://" + digest), payload)
   (cache / digest).write_bytes(b"tampered")
   with self.assertRaisesRegex(ValueError, "checksum"):
    load("local-subtitle://" + digest)

 def test_local_candidate_rejects_bad_hash(self):
  with self.assertRaises(ValueError):
   load("local-subtitle://../../etc/passwd")

if __name__ == "__main__":
 unittest.main()
