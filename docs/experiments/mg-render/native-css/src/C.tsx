import React from 'react';
import {createRoot} from 'react-dom/client';
import {flushSync} from 'react-dom';
import {Scene} from './Scene';

const root=createRoot(document.body.appendChild(document.createElement('div')));
window.paint=async ({data,k,urls})=>{
  flushSync(()=>root.render(<Scene data={data} k={k} media={c=>
    <img src={urls[c.object.object_id]} style={{display:'block',width:'100%',height:'100%'}}/>}/>));
  await Promise.all(Array.from(document.images,i=>i.decode()));
  await document.fonts.ready;
};
