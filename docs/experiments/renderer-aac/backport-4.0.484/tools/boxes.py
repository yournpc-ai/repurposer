"""Read movie, media and edit durations directly from the MP4 (ISO BMFF) boxes."""
import json,struct,sys
from pathlib import Path
def boxes(b):
 i=0
 while i+8<=len(b):
  size,typ=struct.unpack_from('>I4s',b,i)
  if not size: size=len(b)-i
  if size<8:raise ValueError((typ,size))
  yield typ.decode(),b[i+8:i+size]
  i+=size
def clock(b):
 off=20 if b[0] else 12
 return list(struct.unpack_from('>IQ' if b[0] else '>II',b,off))
def inspect(p):
 moov=dict(boxes(p.read_bytes()))['moov']
 out={'movie_scale_duration':clock(dict(boxes(moov))['mvhd'])}
 for name,t in boxes(moov):
  if name!='trak':continue
  tr=dict(boxes(t)); md=dict(boxes(tr['mdia'])); kind=md['hdlr'][8:12].decode()
  edits=dict(boxes(tr['edts']))['elst'];n=struct.unpack_from('>I',edits,4)[0];form='>Qqhh' if edits[0] else '>Iihh'
  out[kind]={'media_scale_duration':clock(md['mdhd']),'edits':[list(x) for x in struct.iter_unpack(form,edits[8:])]}
 return out
if __name__=='__main__':print(json.dumps({s:inspect(Path(s)) for s in sys.argv[1:]},indent=2))
