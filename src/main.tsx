import React, { useState } from 'react';
import { createRoot } from 'react-dom/client';
import { BatteryCharging, ChevronLeft, Clock3, MapPin, Navigation, Package, RotateCcw, Sparkles, Truck, Zap } from 'lucide-react';
import './styles.css';
import './safety.css';

type Form = { soc: string; payload: string; departure: string };
const DRIVER_NAME = '조현수';
type Stop = { name: string; km: number; lounge: boolean; total: number; available: number; output: number; source: string };
type ChargeResult = { stop: Stop; arrivalSoc: number; chargeMin: number; stopTime: Date };
type Result = ChargeResult & { chargingStops: ChargeResult[]; destinationTime: Date; destinationSoc: number; consumption: number; outOfRange: boolean; model: string; safeRoute: boolean; requiredSoc: number };
const formatTime = (date: Date) => new Intl.DateTimeFormat('ko-KR',{hour:'numeric',minute:'2-digit',hour12:true}).format(date);
type ApiStop = { rest_area_name:string; distance_km:number; truck_lounge:boolean; arrival_soc:number; estimated_charge_minutes:number; estimated_arrival_time:string; charger_total:number; charger_available:number; max_output_kw:number; charger_source:string; destination_time:string; destination_soc:number };

function App(){
  const now = new Date(); now.setMinutes(Math.ceil(now.getMinutes()/10)*10);
  const [step,setStep]=useState<'input'|'loading'|'result'>('input');
  const [form,setForm]=useState<Form>({soc:'68',payload:'420',departure:`${String(now.getHours()).padStart(2,'0')}:${String(now.getMinutes()).padStart(2,'0')}`});
  const [altIndex,setAltIndex]=useState(0);
  const [selectedStopIndex,setSelectedStopIndex]=useState(0);
  const [results,setResults]=useState<Result[]>([]);
  const [error,setError]=useState('');
  const result=results[altIndex%Math.max(results.length,1)];
  const activeCharge=result?.chargingStops[Math.min(selectedStopIndex,result.chargingStops.length-1)];
  const valid=Number(form.soc)>=15&&Number(form.soc)<=100&&Number(form.payload)>=0&&Number(form.payload)<=1000&&form.departure;
  const change=(key:keyof Form,value:string)=>setForm({...form,[key]:value});
  const runOptimization=async()=>{
    setError(''); setAltIndex(0); setSelectedStopIndex(0); setStep('loading');
    try{
      const [response]=await Promise.all([fetch('/api/optimize',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({driver_name:DRIVER_NAME,current_soc:Number(form.soc),payload_kg:Number(form.payload),departure_time:form.departure})}),new Promise(r=>setTimeout(r,1200))]);
      if(!response.ok) throw new Error('계산 서버가 응답하지 않습니다.');
      const data=await response.json(); const meta=data.metadata;
      const mapStop=(s:ApiStop):ChargeResult=>({stop:{name:s.rest_area_name,km:s.distance_km,lounge:s.truck_lounge,total:s.charger_total,available:s.charger_available,output:s.max_output_kw,source:s.charger_source},arrivalSoc:s.arrival_soc,chargeMin:s.estimated_charge_minutes,stopTime:new Date(s.estimated_arrival_time)});
      const mapRoute=(r:{charging_stops:ApiStop[];destination_time:string|null;destination_soc:number|null}):Result=>{const chargingStops=r.charging_stops.map(mapStop);const first=chargingStops[0];return {...first,chargingStops,destinationTime:r.destination_time?new Date(r.destination_time):first.stopTime,destinationSoc:r.destination_soc??0,consumption:meta.safe_consumption_kwh_per_100km,outOfRange:meta.payload_out_of_training_range,model:meta.model,safeRoute:data.safe_route_found,requiredSoc:meta.required_destination_soc}};
      setResults([mapRoute(data.recommended_route),...data.alternatives.map(mapRoute)]); setStep('result');
    }catch(e){setError(e instanceof Error?e.message:'계산 중 오류가 발생했습니다.');setStep('input')}
  };
  if(step==='loading') return <main className="app loading"><div className="loaderArt"><span/><span/><span/><div><Truck size={44}/></div></div><h1>최적 루트 계산 중</h1><p>배터리와 적재량을 분석해<br/>가장 효율적인 충전 휴게소를 찾고 있어요.</p><div className="dots"><i/><i/><i/></div></main>;
  if(step==='result') return <main className="app result">
    <header className="topbar"><button className="iconBtn" onClick={()=>setStep('input')} aria-label="입력 화면으로"><ChevronLeft/></button><span>운행 추천 결과</span><button className="iconBtn" onClick={()=>setStep('input')} aria-label="다시 계산"><RotateCcw/></button></header>
    <section className="resultHero"><span className="eyebrow"><Sparkles size={14}/> {result.model} 분석 완료</span><h1><strong>{DRIVER_NAME}</strong> 기사님을 위한<br/>운행 최적화 루트입니다</h1><div className="batteryPill"><BatteryCharging size={17}/> 현재 남은 배터리 <b>{form.soc}%</b></div></section>
    <section className="routeOverview"><small>추천 운행 루트</small><h2>먼저, 오늘의 전체 경로를 확인하세요</h2><div className="routeFlow">{result.chargingStops.map((charge,i)=><React.Fragment key={`${charge.stop.name}-flow`}><button className={selectedStopIndex===i?'active':''} onClick={()=>setSelectedStopIndex(i)}><Zap/> <span>{charge.stop.name}</span><small>{Math.round(charge.chargeMin)}분 충전</small></button><b>→</b></React.Fragment>)}<div className="destinationNode"><MapPin/><span>기장IC 도착</span><small>도착 SOC {Math.round(result.destinationSoc)}%</small></div></div><p>휴게소를 누르면 충전기 현황과 상세 계획을 확인할 수 있어요.</p></section>
    <section className="recommend"><div className="recTitle"><div className="roundIcon"><Zap/></div><div><small>{selectedStopIndex+1}번째 충전 · 휴식 지점</small><h2>{activeCharge.stop.name}에서 충전</h2></div></div>
      <div className="chargeTime"><b>{Math.round(activeCharge.chargeMin)}분</b><span>80%까지 예상 충전 시간</span></div>
      <div className="targetCharge"><span>충전 목표량</span><b>80%</b></div>
      <div className="chargerGrid"><div><b>{activeCharge.stop.total}대</b><span>충전기</span></div><div><b>{activeCharge.stop.available}대</b><span>현재 사용 가능</span></div><div><b>{Math.round(activeCharge.arrivalSoc)}%</b><span>도착 예상 SOC</span></div></div>
      <div className="availability"><i/> 이용 가능성 <b>{activeCharge.stop.available/activeCharge.stop.total>=.7?'매우 높음':'높음'}</b><span>{activeCharge.stop.source==='live'?'환경부 API 현재 상태':'API fallback'}</span></div>
      {activeCharge.stop.lounge&&<div className="lounge"><Truck size={18}/><div><b>화물차 라운지 이용 가능</b><span>충전하는 동안 편하게 쉬어가세요.</span></div></div>}
      <p className="restCopy"><Clock3/> <b>{formatTime(activeCharge.stopTime)}</b> 휴게 예정입니다.</p>
    </section>
    <p className="reserveNotice"><BatteryCharging/> 기장IC 이후 운행을 위한 예비 배터리 10% 포함</p>
    {result.outOfRange&&<p className="warning">500kg 초과 적재량은 XGBoost 학습 범위 밖 외삽 결과입니다. 입력값 {form.payload}kg을 그대로 사용했습니다.</p>}
    {!result.safeRoute&&<p className="warning">현재 조건에서 안전 기준을 만족하는 전체 경로를 찾지 못해 망향휴게소를 fallback으로 표시합니다.</p>}
    <div className="eta"><span>{result.safeRoute?'예상 도착 시간':'경로 상태'}</span><b>{result.safeRoute?formatTime(result.destinationTime):'재계산 필요'}</b><small>도착 최소 기준 {result.requiredSoc}% · 202km 노선</small></div>
    {results.length>1&&<button className="primary" onClick={()=>{setAltIndex(i=>i+1);setSelectedStopIndex(0)}}>다른 추천안 확인하기 <Navigation size={18}/></button>}
    <p className="disclaimer">차량 제원 기반 근사 결과이며, 실제 주행 환경과 충전기 상태에 따라 달라질 수 있습니다.</p>
  </main>;
  return <main className="app input">
    <header className="brand"><div><Zap size={18}/></div><span>EV ROUTE</span><small>봉고 EV 운행 최적화</small></header>
    <section className="intro"><span className="eyebrow">전기화물차 운행 최적화</span><h1>어서오세요,<br/><strong>{DRIVER_NAME} 기사님</strong></h1><p>현재 차량 상태를 입력하시면 충전과 휴식을 함께 고려한 운행 루트를 안내해 드릴게요.</p></section>
    <div className="truckVisual"><div className="road"/><div className="truckIcon"><Truck size={62}/><Zap size={23}/></div><span className="routeDot one"/><span className="routeDot two"/></div>
    <form onSubmit={e=>{e.preventDefault();if(valid)void runOptimization()}}>
      <div className="formRow"><label>현재 배터리 잔량<div className="field"><BatteryCharging/><input type="number" min="15" max="100" value={form.soc} onChange={e=>change('soc',e.target.value)}/><em>%</em></div></label><label>오늘의 적재 중량<div className="field"><Package/><input type="number" min="0" max="1000" value={form.payload} onChange={e=>change('payload',e.target.value)}/><em>kg</em></div></label></div>
      <label>출발 시간<div className="field"><Clock3/><input type="time" value={form.departure} onChange={e=>change('departure',e.target.value)}/></div></label>
      <button className="primary" disabled={!valid}>최적 루트 계산하기 <Navigation size={19}/></button>
    </form>{error&&<p className="warning">{error}</p>}<p className="hint"><Sparkles/> XGBoost와 실시간 충전소 현황을 함께 분석합니다</p>
  </main>
}
createRoot(document.getElementById('root')!).render(<React.StrictMode><App/></React.StrictMode>);
