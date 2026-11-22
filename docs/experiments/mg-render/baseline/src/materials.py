from fractions import Fraction
from pathlib import Path
import os, json, wave, hashlib
import numpy as np, av, cv2
from PIL import Image,ImageDraw,ImageFont
R=Path('assets')
def video(name, rate, size, length):
    w,h=size
    font=ImageFont.truetype(os.environ['FONT'],max(13,w//55))
    bg=Image.new('RGB',size,'#16353c' if name=='main' else '#e0decc'); d=ImageDraw.Draw(bg)
    ink='#a8c8bc' if name=='main' else '#294846'
    for x in range(0,w,40):d.line((x,0,x,h),fill='#28464b' if name=='main' else '#b8c3b8')
    for y in range(0,h,40):d.line((0,y,w,y),fill='#28464b' if name=='main' else '#b8c3b8')
    d.text((22,44),'FIELD RECORDING    /    WEST RIDGE' if name=='main' else 'SENSOR B    /    PHASE',font=font,fill=ink)
    with av.open(str(R/(name+'.mp4')),'w') as out:
        st=out.add_stream('libx264',rate=rate);st.width=w;st.height=h;st.pix_fmt='yuv420p';st.options={'crf':'14','preset':'fast','threads':'2'}
        for i in range(length):
            im=bg.copy();d=ImageDraw.Draw(im)
            for line in range(13 if name=='main' else 3):
                xx=np.arange(0,w,3); u=xx/w
                v=(0.37+line*.032 if name=='main' else .45+line*.12)+.085*np.sin(6*u+i*.012+line*.18)+.026*np.sin(25*u-line*.1+i*.023)
                pts=list(zip(xx.tolist(),(h*v).astype(int).tolist()));d.line(pts,fill=('#e1b87d' if line==4 else ink),width=2)
            for bit in range(10):
                x=12+bit*12;d.rectangle((x,10,x+9,24),fill='white' if i & 1<<bit else 'black')
            d.text((w-90,h-34),f'{i:04}',font=font,fill=ink)
            fr=av.VideoFrame.from_image(im)
            for pkt in st.encode(fr):out.mux(pkt)
        for pkt in st.encode():out.mux(pkt)
def write_wav(path,x):
    with wave.open(str(path),'wb') as f:
        f.setparams((1,2,48000,0,'NONE','not compressed'));f.writeframes((np.clip(x,-1,1)*32767).round().astype('<i2').tobytes())
def recipe(kind,body):
    start=__import__('time').perf_counter()
    t=np.arange(int(48000*body['seconds']))/48000
    rng=np.random.default_rng(body['seed'])
    if kind=='whoosh':
        noise=rng.standard_normal(t.size);x=.29*np.diff(noise,prepend=0)*np.sin(np.pi*t/body['seconds'])**2/4
    else:
        phase=2*np.pi*(body['hz']*t+3*(1-np.exp(-t*25)))
        x=.52*np.cos(phase)*np.exp(-t/body['decay'])+.12*rng.uniform(-1,1,t.size)*np.exp(-t/.022)
    write_wav(R/(body['file']),x)
    return __import__('time').perf_counter()-start
if __name__=='__main__':
    video('main',Fraction(24000,1001),(960,540),213)
    video('pip',Fraction(25),(480,270),184)
    recipes={};times={}
    for key,desc in [('whoosh',dict(seed=241,seconds=1.2)),('impact1',dict(seed=71,hz=100,decay=.12,seconds=.8)),('impact2',dict(seed=71,hz=64,decay=.22,seconds=.8))]:
        desc['file']=key+'.wav'; recipes[key]=desc;times[key]=recipe('whoosh' if key=='whoosh' else 'impact',desc)
    Path('fixture/recipes.json').write_text(json.dumps(recipes,indent=2));Path('logs/recipe-seconds.json').write_text(json.dumps(times))
