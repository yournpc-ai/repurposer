import React from 'react';
import {createRoot} from 'react-dom/client';
import {flushSync} from 'react-dom';
import {Aperture,Caption} from './Boundary';
const root=createRoot(document.body.appendChild(document.createElement('div')));
(window as any).paint=async(props:any)=>{
  flushSync(()=>root.render(<><Aperture {...props}><div style={{width:'100%',height:'100%',background:'white'}}/></Aperture>
    <div style={{position:'absolute',left:580,top:0}}><Caption {...props}/></div></>));
  await document.fonts.ready;
};
