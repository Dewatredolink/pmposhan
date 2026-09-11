import { useEffect, useState } from 'react';

type Props={lang:'mr'|'en'};
const read=(k:string,d='')=>localStorage.getItem(k)||d;
function fileToDataUrl(file:File){return new Promise<string>((resolve,reject)=>{const r=new FileReader();r.onload=()=>resolve(String(r.result||''));r.onerror=reject;r.readAsDataURL(file);});}

export default function BrandingSettings({lang}:Props){
  const mr=lang==='mr';
  const [schoolLogo,setSchoolLogo]=useState(()=>read('pmposhan.brand.schoolLogo'));
  const [districtLogo,setDistrictLogo]=useState(()=>read('pmposhan.brand.districtLogo'));
  const [districtName,setDistrictName]=useState(()=>read('pmposhan.brand.districtName','District / जिल्हा'));
  const [departmentName,setDepartmentName]=useState(()=>read('pmposhan.brand.departmentName','School Education & Sports Department'));
  const [saved,setSaved]=useState(false);
  useEffect(()=>{setSaved(false)},[schoolLogo,districtLogo,districtName,departmentName]);
  async function pick(kind:'school'|'district',f?:File){if(!f)return;if(!['image/png','image/jpeg','image/webp','image/svg+xml'].includes(f.type)){alert(mr?'PNG/JPG/WEBP/SVG प्रतिमा निवडा.':'Choose PNG/JPG/WEBP/SVG image.');return;}if(f.size>2*1024*1024){alert(mr?'लोगो 2 MB पेक्षा कमी असावा.':'Logo must be under 2 MB.');return;}const url=await fileToDataUrl(f); kind==='school'?setSchoolLogo(url):setDistrictLogo(url)}
  function save(){localStorage.setItem('pmposhan.brand.schoolLogo',schoolLogo);localStorage.setItem('pmposhan.brand.districtLogo',districtLogo);localStorage.setItem('pmposhan.brand.districtName',districtName);localStorage.setItem('pmposhan.brand.departmentName',departmentName);setSaved(true);window.dispatchEvent(new Event('pmposhan-branding-changed'));}
  function clearLogo(kind:'school'|'district'){if(kind==='school')setSchoolLogo('');else setDistrictLogo('')}
  return <main className="content ui-page">
    <div className="ui-page-head"><div><span className="ui-eyebrow">{mr?'प्रशासन':'ADMINISTRATION'}</span><h2>{mr?'ब्रँडिंग व लोगो':'Branding & Logos'}</h2><p>{mr?'शाळा आणि जिल्ह्याचे लोगो व शीर्षक बदला.':'Configure school and district branding shown across the application.'}</p></div></div>
    <section className="panel brand-settings-card">
      <div className="brand-form-grid">
        <label><span>{mr?'जिल्ह्याचे नाव':'District name'}</span><input value={districtName} onChange={e=>setDistrictName(e.target.value)} placeholder="Palghar / पालघर"/></label>
        <label><span>{mr?'विभागाचे नाव':'Department name'}</span><input value={departmentName} onChange={e=>setDepartmentName(e.target.value)}/></label>
      </div>
      <div className="logo-upload-grid">
        <LogoBox title={mr?'शाळेचा लोगो':'School logo'} value={schoolLogo} onPick={f=>pick('school',f)} onClear={()=>clearLogo('school')} mr={mr}/>
        <LogoBox title={mr?'जिल्ह्याचा लोगो':'District logo'} value={districtLogo} onPick={f=>pick('district',f)} onClear={()=>clearLogo('district')} mr={mr}/>
      </div>
      <div className="notice">{mr?'सुचविलेले: पारदर्शक PNG किंवा SVG, चौरस स्वरूप, किमान 256×256. लोगो या ब्राउझरमध्ये सुरक्षित केला जातो.':'Recommended: transparent PNG or SVG, square format, at least 256×256. Logos are saved in this browser.'}</div>
      <div className="action-row"><button className="primary" onClick={save}>{mr?'ब्रँडिंग जतन करा':'Save branding'}</button></div>
      {saved&&<div className="success-box">{mr?'ब्रँडिंग यशस्वीपणे जतन केले.':'Branding saved successfully.'}</div>}
    </section>
  </main>
}

function LogoBox({title,value,onPick,onClear,mr}:{title:string;value:string;onPick:(f?:File)=>void;onClear:()=>void;mr:boolean}){
 return <div className="logo-upload-card"><div className="logo-preview">{value?<img src={value} alt={title}/>:<span>🏫</span>}</div><div><h3>{title}</h3><p>{mr?'PNG / JPG / WEBP / SVG':'PNG / JPG / WEBP / SVG'}</p><label className="upload-button">{mr?'प्रतिमा निवडा':'Choose image'}<input type="file" accept="image/png,image/jpeg,image/webp,image/svg+xml" onChange={e=>onPick(e.target.files?.[0])}/></label>{value&&<button className="link-button" onClick={onClear}>{mr?'काढून टाका':'Remove'}</button>}</div></div>
}
