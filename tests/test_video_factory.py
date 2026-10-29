import copy, json, math, shutil, subprocess, tempfile, unittest
from pathlib import Path
from scripts.video_factory import validate, require_approval, sha256, mix, inspect, rms_db
ROOT=Path(__file__).resolve().parents[1]
class ProjectTests(unittest.TestCase):
 def setUp(self): self.p=json.loads((ROOT/"examples/mutual/project.json").read_text())
 def test_mutual_82s_twenty_windows(self):
  validate(self.p); self.assertEqual(len(self.p["scenes"]),20); self.assertEqual(self.p["scenes"][-1]["end"],82.3)
 def test_overlap_rejected(self):
  self.p["scenes"][1]["start"]=0
  with self.assertRaises(ValueError): validate(self.p)
 def test_invalid_duration_rejected(self):
  for d in (0,-1,float("nan"),float("inf")):
   p=copy.deepcopy(self.p); p["duration"]=d
   with self.assertRaises(ValueError): validate(p)
 def test_agent_cannot_approve(self):
  self.p["approvals"]["preview"]={"actor":"agent","approved":True,"evidence":"x"}
  with self.assertRaises(ValueError): require_approval(self.p,"preview",{})
 def test_asset_change_invalidates_approval(self):
  with tempfile.TemporaryDirectory() as d:
   f=Path(d)/"script"; f.write_text("ok")
   self.p["approvals"]["script_storyboard"]={"actor":"human","approved":True,"evidence":"fixture","hashes":{"script":sha256(f)}}
   require_approval(self.p,"script_storyboard",{"script":f}); f.write_text("changed")
   with self.assertRaises(ValueError): require_approval(self.p,"script_storyboard",{"script":f})
@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"),"Requires FFmpeg")
class AudioTests(unittest.TestCase):
 def test_mix_and_inspect(self):
  with tempfile.TemporaryDirectory() as d:
   v,m,o=[Path(d)/(n+".wav") for n in ("voice","music","out")]
   for p,hz,dur in ((v,440,2),(m,220,1)): subprocess.run(["ffmpeg","-v","error","-f","lavfi","-i",f"sine=frequency={hz}:duration={dur}",str(p)],check=True)
   result=mix(v,m,o,2); self.assertAlmostEqual(result["music_gain_db"],-16,delta=.2)
   self.assertGreater(rms_db(o),-40); self.assertEqual(inspect(o,2)["streams"][0]["codec_name"],"pcm_s16le")
   with self.assertRaises(ValueError): inspect(o,3)
 def test_silence_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/"silent.wav"; subprocess.run(["ffmpeg","-v","error","-f","lavfi","-i","anullsrc=r=48000:cl=mono","-t","1",str(p)],check=True)
   with self.assertRaises(ValueError): rms_db(p)
if __name__=="__main__": unittest.main()
