import wave,numpy as np
def pcm(spec):
    rate=spec['sample_rate'];fps=spec['fps']['num'];out=np.zeros((spec['duration_frames']*rate//fps,2))
    for tr in spec['tracks']:
        if tr['kind']!='audio':continue
        for c in tr['clips']:
            a,b=[c[k]*rate//fps for k in ('start_frame','end_frame')];offset=c['source']['start_frame']*rate//fps
            with wave.open('assets/'+c['source']['url'],'rb') as f:
                assert (f.getframerate(),f.getnchannels(),f.getsampwidth())==(rate,1,2)
                f.setpos(offset);x=np.frombuffer(f.readframes(b-a),'<i2')/32768
            out[a:b]+=x[:,None]*10**(c['object']['gain_db']/20)/np.sqrt(2)
    return out
