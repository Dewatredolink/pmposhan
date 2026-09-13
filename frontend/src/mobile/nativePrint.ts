import { Capacitor, registerPlugin } from '@capacitor/core';

type PrintOptions={jobName?:string};
type NativePrintPlugin={print(options?:PrintOptions):Promise<{started?:boolean}>};

const NativePrint=registerPlugin<NativePrintPlugin>('NativePrint');

export async function printCurrentView(jobName='PM POSHAN'):Promise<void>{
  if(Capacitor.getPlatform()==='android'){
    try{
      await NativePrint.print({jobName});
      return;
    }catch(error){
      console.warn('Native Android print unavailable; falling back to window.print()',error);
    }
  }
  window.print();
}
