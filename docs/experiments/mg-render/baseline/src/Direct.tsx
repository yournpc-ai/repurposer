import React from 'react';
import {createRoot} from 'react-dom/client';
import {flushSync} from 'react-dom';
import {Title} from './active-title';
const root=createRoot(document.getElementById('root')!);
(window as any).draw=async (args:any)=>{
  flushSync(()=>root.render(<Title {...args}/>));
  await document.fonts.ready;
};
