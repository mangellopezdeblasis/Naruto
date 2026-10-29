"""Helpers deterministas de audio y QA para Naruto; sin proveedores pagos."""
import argparse, hashlib, json, math, re, subprocess
from pathlib import Path

def run(args):
    return subprocess.run(args, check=True, capture_output=True, text=True).stderr

def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def validate(project):
    d=project["duration"]
    if not isinstance(d,(int,float)) or not math.isfinite(d) or d<=0: raise ValueError("Duración inválida")
    previous=0
    if not project.get("scenes"): raise ValueError("Faltan escenas")
    for scene in project["scenes"]:
        a,b=scene["start"],scene["end"]
        if not all(isinstance(x,(int,float)) and math.isfinite(x) for x in (a,b)) or not previous<=a<b<=d:
            raise ValueError("Ventana inválida, superpuesta o fuera de duración")
        if not scene.get("text","").strip(): raise ValueError("Falta texto")
        previous=b
    offset=project.get("music_offset_db",-16)
    if not isinstance(offset,(int,float)) or not math.isfinite(offset) or offset>0: raise ValueError("Nivel de música inválido")

def require_approval(project,stage,assets):
    approval=project.get("approvals",{}).get(stage,{})
    if approval.get("actor")!="human" or approval.get("approved") is not True or not approval.get("evidence","").strip():
        raise ValueError("Falta aprobación humana: "+stage)
    for name,path in assets.items():
        if approval.get("hashes",{}).get(name)!=sha256(path): raise ValueError("Aprobación desactualizada: "+name)

def rms_db(path):
    report=run(["ffmpeg","-hide_banner","-nostats","-i",str(path),"-vn","-af","volumedetect","-f","null","-"])
    match=re.search(r"mean_volume: ([-\\w.]+) dB",report)
    if not match or float(match[1])<=-90: raise ValueError("Audio silencioso o sin medición")
    return float(match[1])

def mix(voice,music,output,duration,offset=-16):
    if not math.isfinite(duration) or duration<=0 or not math.isfinite(offset) or offset>0: raise ValueError("Duración/nivel inválido")
    if Path(output).exists(): raise ValueError("La salida ya existe")
    gain=rms_db(voice)+offset-rms_db(music); fade=min(1.5,duration)
    graph=(f"[0:a]apad,atrim=duration={duration},asetpts=PTS-STARTPTS[v];"
           f"[1:a]atrim=duration={duration},asetpts=PTS-STARTPTS,volume={gain}dB,afade=t=out:st={duration-fade}:d={fade}[m];"
           "[v][m]amix=inputs=2:normalize=0:duration=first,alimiter=limit=0.95:level=0:latency=1[out]")
    run(["ffmpeg","-nostdin","-v","error","-i",str(voice),"-stream_loop","-1","-i",str(music),
         "-filter_complex",graph,"-map","[out]","-t",str(duration),"-c:a","pcm_s16le",str(output)])
    return {"voice_rms_db":rms_db(voice),"music_gain_db":gain,"target_offset_db":offset,"mixed_rms_db":rms_db(output)}

def inspect(path,expected=None):
    info=json.loads(subprocess.check_output(["ffprobe","-v","error","-show_format","-show_streams","-of","json",str(path)],text=True))
    if expected is not None and abs(float(info["format"]["duration"])-expected)>.15: raise ValueError("Duración fuera de tolerancia")
    if not any(s["codec_type"]=="audio" for s in info["streams"]): raise ValueError("Falta audio")
    run(["ffmpeg","-v","error","-xerror","-i",str(path),"-f","null","-"])
    report=run(["ffmpeg","-hide_banner","-nostats","-i",str(path),"-vn","-af","volumedetect","-f","null","-"])
    peak=re.search(r"max_volume: ([-\\w.]+) dB",report)
    if not peak or float(peak[1])>=0: raise ValueError("Pico sin margen o medición ausente")
    info["peak_dbfs"]=float(peak[1]); info["audio_rms_db"]=rms_db(path)
    info["limitations"]="No valida sincronía, voz percibida ni máscara visual."
    return info

def main():
    parser=argparse.ArgumentParser(); subs=parser.add_subparsers(dest="cmd",required=True)
    val=subs.add_parser("validate"); val.add_argument("project")
    m=subs.add_parser("mix")
    for f in ("project","voice","music","output"): m.add_argument("--"+f,required=True)
    q=subs.add_parser("inspect"); q.add_argument("path"); q.add_argument("--duration",type=float)
    args=parser.parse_args()
    if args.cmd=="inspect": print(json.dumps(inspect(args.path,args.duration),indent=2)); return
    path=Path(args.project); project=json.loads(path.read_text()); validate(project)
    if args.cmd=="validate": print("Ventanas válidas; falta completar y aprobar guion."); return
    require_approval(project,"script_storyboard",{k:path.parent/project[k] for k in ("script","storyboard")})
    if any("PENDIENTE" in s["text"] for s in project["scenes"]): raise ValueError("Guion incompleto")
    print(json.dumps(mix(args.voice,args.music,args.output,project["duration"],project.get("music_offset_db",-16)),indent=2))
if __name__=="__main__": main()
