"""Original DSP. No samples or third-party recipes. Run inside the evidence directory."""
from pathlib import Path
import wave, hashlib, json, platform, io, sys
import numpy as np
from catalog import catalog

RATE = 48000
def dump(path, obj):
    Path(path).write_text(json.dumps(obj,ensure_ascii=False,sort_keys=True,indent=2)+"\n")

def digest(data):
    return hashlib.sha256(data).hexdigest()

def pcm_wave(x):
    assert np.isfinite(x).all() and abs(x).max()<1
    out=io.BytesIO()
    with wave.open(out,"wb") as w:
        w.setparams((x.shape[1],2,RATE,0,"NONE",""))
        w.writeframes(np.rint(x*32767).astype("<i2").tobytes())
    return out.getvalue()

def band(noise, center, spread):
    # Gaussian band from seeded noise, shaped independently of the tonal layer.
    f=np.fft.rfftfreq(len(noise),1/RATE)
    weights=np.exp(-0.5*((f-center)/spread)**2)
    y=np.fft.irfft(np.fft.rfft(noise)*weights,n=len(noise))
    return y / np.sqrt(np.mean(y*y))

def synth(key, overrides, seed=1248):
    schema=catalog[key]["parameters"]["properties"]
    if set(overrides)-set(schema) or type(seed)!=int or not 0<=seed<2**32:
        raise ValueError("unknown control or invalid seed")
    p={k:overrides.get(k,v["default"]) for k,v in schema.items()}
    for k,v in p.items():
        if type(v)!=int or not schema[k]["minimum"]<=v<=schema[k]["maximum"]:
            raise ValueError(k)
    ms=p.get("duration",p.get("tail",65))
    t=np.arange(ms*48)/RATE
    u=np.linspace(0,1,len(t))
    rng=np.random.Generator(np.random.PCG64(seed))
    if key=="whoosh":
        noise=rng.standard_normal(len(t))
        travel=p["travel"]/100
        shine=p["tone"]/100
        freq=p["pitch"]
        body=band(noise,freq,0.47*freq)
        air=band(noise,800+3100*shine,350+520*shine)
        phase=2*np.pi*np.cumsum(freq*(0.48+travel*u))/RATE
        envelope=np.sin(np.pi*u)**1.65
        y=envelope*(0.085*body*(1-u)+0.16*shine*air*np.sin(np.pi*u)**2+0.04*np.sin(phase))
        pan=(2*u-1)*travel
        x=np.stack([y*np.sqrt((1-pan)/2),y*np.sqrt((1+pan)/2)],axis=1)
    elif key=="impact":
        punch=p["punch"]/100
        phase=2*np.pi*(p["body"]*t+1.5*(1-np.exp(-65*t)))
        attack=1-np.exp(-t/(0.008-0.006*punch))
        y=attack*(0.36*np.sin(phase)*np.exp(-6*u)+punch*0.16*np.sin(3.3*phase)*np.exp(-85*t))
        x=np.column_stack([y,y])
        for channel,delay,weight in [(0,11,.32),(1,17,.28),(0,30,.13),(1,39,.14)]:
            shift=delay*48
            x[shift:,channel]+=weight*p["space"]/100*y[:-shift]
    else:
        h=p["hardness"]/100
        phase=2*np.pi*p["pitch"]*(t+0.0012*(1-np.exp(-230*t)))
        y=(1-np.exp(-t/(.0045-.0037*h)))*np.exp(-86*t)*(
            .31*np.sin(phase)+.16*h*np.sin(2.72*phase)*np.exp(-130*t))
        x=np.column_stack([y,y])
    x*=np.sin(np.pi/2*np.minimum(1,(1-u)*ms/6))[:,None]**2
    source=dict(recipe_id=key,recipe_version=1,params=p,seed=seed,dsp="repurposer-research-1",
                source_files={s:digest(Path(s).read_bytes()) for s in ("render.py","catalog.py")},
                rate=RATE,channels=2,format="wav-pcm-s16le",numpy=np.__version__,
                python=platform.python_version(),machine=platform.machine(), system=platform.system())
    return pcm_wave(x),source

edits={"whoosh":{"tone":22},"impact":{"body":75},"click":{"hardness":14}}
if __name__=="__main__":
    dump("catalog.json",catalog)
    sources={}
    for key in catalog:
        for label,changes in [("default",{}),("rev",edits[key])]:
            name=f"{key}-{label}"
            data,source=synth(key,changes)
            assert synth(key,changes)[0]==data
            Path(name+".wav").write_bytes(data)
            fingerprint=json.dumps(source,sort_keys=True,separators=(",",":")).encode()
            sources[name]={"source":source,"spec_sha256":digest(fingerprint),"wav_sha256":digest(data)}
    dump("sources.json",sources)
