import { Capacitor, registerPlugin } from '@capacitor/core';

type NativeFilePlugin={
  save(options:{fileName:string;mimeType:string;base64:string}):Promise<{saved:boolean;uri?:string;location?:string}>;
};

const NativeFile=registerPlugin<NativeFilePlugin>('NativeFile');

function bytesToBase64(bytes:Uint8Array):string{
  let binary='';
  const chunk=0x8000;
  for(let i=0;i<bytes.length;i+=chunk){
    binary+=String.fromCharCode(...bytes.subarray(i,Math.min(i+chunk,bytes.length)));
  }
  return btoa(binary);
}

export async function saveBlobToDevice(blob:Blob,fileName:string):Promise<{location?:string}>{
  if(Capacitor.getPlatform()==='android'){
    const bytes=new Uint8Array(await blob.arrayBuffer());
    const result=await NativeFile.save({
      fileName,
      mimeType:blob.type||'application/octet-stream',
      base64:bytesToBase64(bytes),
    });
    if(!result.saved)throw new Error('ANDROID_FILE_SAVE_FAILED');
    return {location:result.location||result.uri};
  }
  const url=URL.createObjectURL(blob);
  const a=document.createElement('a');
  a.href=url;
  a.download=fileName;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(()=>URL.revokeObjectURL(url),1000);
  return {};
}
