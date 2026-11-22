import wave
from pathlib import Path
import numpy as np
import av
from render import dump,digest,RATE

def wav(path):
    with wave.open(str(path)) as w:
        assert w.getframerate()==RATE and w.getsampwidth()==2 and w.getnchannels()==2
        return np.frombuffer(w.readframes(w.getnframes()),"<i2").reshape(-1,2)/32768

def db(x):
    return round(20*np.log10(max(1e-12,float(x))),3)

def decode(path,rate=RATE):
    with av.open(str(path)) as c:
        stream=c.streams.audio[0]
        resampler=av.AudioResampler(format="fltp",layout="stereo",rate=rate)
        blocks=[]
        for frame in c.decode(stream):
            blocks.extend(resampler.resample(frame))
        blocks.extend(resampler.resample(None))
        start=float(blocks[0].pts*blocks[0].time_base)
        return start,np.concatenate([b.to_ndarray().T for b in blocks])

def measure(path):
    x=wav(path)
    power=np.abs(np.fft.rfft(x,axis=0))**2
    bins=np.fft.rfftfreq(len(x),1/RATE)
    energy=power.sum(axis=1)
    over=decode(path,4*RATE)[1]
    return dict(rate=RATE,channels=2,samples=len(x),ms=len(x)/48,
                peak_dbfs=db(abs(x).max()),true_peak_estimate_dbTP=db(abs(over).max()),
                rms_dbfs=db(np.sqrt(np.mean(x*x))),rail_samples=int(np.sum((x>=32767/32768)|(x<=-1))),
                edge_lsb=np.rint(x[[0,-1]]*32768).astype(int).tolist(),
                edge_step_lsb=np.rint((x[[1,-1]]-x[[0,-2]])*32768).astype(int).tolist(),
                tail_5ms_rms_dbfs=db(np.sqrt(np.mean(x[-240:]**2))),
                peak_sample=int(abs(x).max(axis=1).argmax()),energy_centroid_hz=round(np.average(bins,weights=energy),1),
                dominant_hz=round(bins[energy.argmax()],1),sha256=digest(path.read_bytes()))
if __name__=="__main__":
    m={p.stem:measure(p) for p in sorted(Path(".").glob("*-*.wav")) if p.stem.endswith(("-default","-rev"))}
    dump("measurements.json",m)
    for k,v in m.items():
        print(k,*[v[j] for j in ("ms","peak_dbfs","true_peak_estimate_dbTP","rms_dbfs","tail_5ms_rms_dbfs","peak_sample","energy_centroid_hz","dominant_hz","edge_step_lsb")])
