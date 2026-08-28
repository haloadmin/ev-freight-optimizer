from __future__ import annotations

import csv
import os
from urllib.parse import unquote
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import numpy as np
import xgboost as xgb
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
load_dotenv(ROOT / ".env")
MODEL_PATH = BACKEND / "model" / "ev_best_model_compatible.ubj"
ROUTE_PATH = BACKEND / "data" / "fixed_route_rest_areas.csv"
EV_API_BASE_URL = os.getenv("EV_API_BASE_URL", "https://apis.data.go.kr/B552584/EvCharger").rstrip("/")
EV_API_KEY = unquote(os.getenv("api_key") or os.getenv("EV_API_KEY", ""))

FEATURES = ["평균 주행 속도", "적재/탑승 중량", "외기 온도", "냉난방 소비 전력", "도로 경사도", "배터리 온도", "운전 성향 지수", "타이어 공기압", "주행 거리"]
BASE_CONDITION = {"평균 주행 속도":100.0,"적재/탑승 중량":248.82,"외기 온도":15.59,"냉난방 소비 전력":2.477,"도로 경사도":1.464,"배터리 온도":29.97,"운전 성향 지수":0.500,"타이어 공기압":2.8,"주행 거리":200.0}
BATTERY_KWH, BONGO_BASE_CONSUMPTION, AVG_SPEED_KMH = 60.4, 100 / 2.7, 80
TARGET_SOC, CRITICAL_SOC = 80, 10
ROUTE_TOTAL_KM, ONWARD_DISTANCE_KM, CONSUMPTION_UNCERTAINTY = 202, 10, 1.10
if not MODEL_PATH.exists(): raise RuntimeError(f"Model not found: {MODEL_PATH}")
MODEL = xgb.Booster()
MODEL.load_model(MODEL_PATH)
MODEL_NAME = "XGBRegressor"

class OptimizeRequest(BaseModel):
    driver_name: str = Field(min_length=1, max_length=30)
    current_soc: float = Field(ge=15, le=100)
    payload_kg: float = Field(ge=0, le=1000)
    departure_time: str

def load_route() -> list[dict[str, Any]]:
    rows=[]
    with ROUTE_PATH.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            rows.append({"name":row["rest_area_name"],"km":float(row["distance_from_anseong_km"] or 0),"lounge":row["truck_lounge_flag"]=="1"})
    return rows

def prediction(payload: float) -> tuple[float,float,bool]:
    current=BASE_CONDITION.copy(); current["적재/탑승 중량"]=payload
    base_values=np.asarray([[BASE_CONDITION[c] for c in FEATURES]],dtype=np.float32)
    current_values=np.asarray([[current[c] for c in FEATURES]],dtype=np.float32)
    base_pred=float(MODEL.predict(xgb.DMatrix(base_values,feature_names=FEATURES))[0])
    current_pred=float(MODEL.predict(xgb.DMatrix(current_values,feature_names=FEATURES))[0])
    ratio=current_pred/base_pred if base_pred>0 else 1.0
    return BONGO_BASE_CONSUMPTION*ratio,ratio,payload>500

def api_items(payload: dict[str,Any]) -> list[dict[str,Any]]:
    body=payload.get("items",payload.get("body",{}).get("items",{})); items=body.get("item",body) if isinstance(body,dict) else body
    return [items] if isinstance(items,dict) else items if isinstance(items,list) else []

async def charger_snapshot(route: list[dict[str,Any]]) -> tuple[dict[str,dict[str,Any]],bool]:
    if not EV_API_KEY: return {},False
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            response=await client.get(f"{EV_API_BASE_URL}/getChargerInfo",params={"serviceKey":EV_API_KEY,"pageNo":1,"numOfRows":9999,"dataType":"JSON"})
            response.raise_for_status(); items=api_items(response.json())
    except Exception: return {},False
    result={}
    for stop in route:
        key=stop["name"].replace("휴게소",""); matched=[x for x in items if key in str(x.get("statNm",""))]
        if not matched: continue
        available=sum(str(x.get("stat",""))=="2" for x in matched); in_use=sum(str(x.get("stat",""))=="3" for x in matched)
        outputs=[float(x.get("output") or 0) for x in matched if str(x.get("output") or "").replace(".","",1).isdigit()]
        result[stop["name"]]={"total":len(matched),"available":available,"in_use":in_use,"unavailable":len(matched)-available-in_use,"max_output_kw":max(outputs,default=0),"source":"live"}
    return result,True

def fallback_chargers(name: str) -> dict[str,Any]:
    p={"안성휴게소":(6,3,200),"망향휴게소":(4,1,100),"천안호두휴게소":(8,4,200),"옥산휴게소":(10,6,200),"죽암휴게소":(6,2,100),"옥천휴게소":(8,5,200),"금강휴게소":(4,1,100),"황간휴게소":(6,3,200),"추풍령휴게소":(8,6,200),"김천휴게소":(10,7,200),"칠곡휴게소":(8,5,200)}
    total,available,output=p.get(name,(4,2,100)); return {"total":total,"available":available,"in_use":total-available,"unavailable":0,"max_output_kw":output,"source":"fallback"}

def parse_departure(value: str) -> datetime:
    try: h,m=map(int,value.split(":")); return datetime.now().replace(hour=h,minute=m,second=0,microsecond=0)
    except Exception as exc: raise HTTPException(422,"출발 시간 형식은 HH:MM이어야 합니다.") from exc

app=FastAPI(title="EV Freight Route Optimizer",version="1.0.0")
app.add_middleware(CORSMiddleware,allow_origins=["http://localhost:5173"],allow_methods=["*"],allow_headers=["*"])

@app.get("/api/health")
def health(): return {"ok":True,"model":MODEL_NAME,"charger_api_configured":bool(EV_API_KEY)}

@app.post("/api/optimize")
async def optimize(req: OptimizeRequest):
    route=load_route(); consumption,correction_ratio,out_of_range=prediction(req.payload_kg); live,api_ok=await charger_snapshot(route); departure=parse_departure(req.departure_time)
    safe_consumption=consumption*CONSUMPTION_UNCERTAINTY
    required_destination_soc=CRITICAL_SOC+safe_consumption*ONWARD_DISTANCE_KM/BATTERY_KWH
    charge_nodes=[]
    for stop in route[1:-1]:
        charger=live.get(stop["name"],fallback_chargers(stop["name"]))
        if charger["available"]>0: charge_nodes.append({**stop,**charger})
    def soc_drop(distance_km): return safe_consumption*distance_km/BATTERY_KWH
    def simulate(selected):
        soc=req.current_soc; previous_km=0.0; elapsed_minutes=0.0; plan=[]
        for stop in selected:
            segment=stop["km"]-previous_km; soc-=soc_drop(segment); elapsed_minutes+=segment/AVG_SPEED_KMH*60
            if soc<CRITICAL_SOC: return None
            charge_minutes=max(0.0,(TARGET_SOC-soc)*32/70); arrival_time=departure+timedelta(minutes=elapsed_minutes); elapsed_minutes+=charge_minutes
            plan.append({**stop,"arrival_soc":soc,"charge_minutes":charge_minutes,"arrival_time":arrival_time}); soc=TARGET_SOC; previous_km=stop["km"]
        final_segment=ROUTE_TOTAL_KM-previous_km; soc-=soc_drop(final_segment); elapsed_minutes+=final_segment/AVG_SPEED_KMH*60
        if soc<required_destination_soc: return None
        total_charge=sum(x["charge_minutes"] for x in plan); service_bonus=sum((x["available"]/max(x["total"],1))*3+(1 if x["lounge"] else 0) for x in plan)
        return {"plan":plan,"destination_soc":soc,"destination_time":departure+timedelta(minutes=elapsed_minutes),"total_charge_minutes":total_charge,"cost":total_charge+len(plan)*2-service_bonus*.35}
    feasible=[]
    for mask in range(1<<len(charge_nodes)):
        selected=[charge_nodes[i] for i in range(len(charge_nodes)) if mask&(1<<i)]; result=simulate(selected)
        if result: feasible.append(result)
    feasible.sort(key=lambda x:(x["cost"],len(x["plan"]),-x["destination_soc"])); safe_route_found=bool(feasible)
    if not feasible:
        fallback=next((x for x in charge_nodes if x["name"]=="망향휴게소"),None)
        if fallback:
            arrival=req.current_soc-soc_drop(fallback["km"]); charge=max(0.0,(TARGET_SOC-max(0,arrival))*32/70)
            feasible=[{"plan":[{**fallback,"arrival_soc":arrival,"charge_minutes":charge,"arrival_time":departure+timedelta(hours=fallback["km"]/AVG_SPEED_KMH)}],"destination_soc":None,"destination_time":None,"total_charge_minutes":charge,"cost":9999}]
        else: raise HTTPException(422,"안전 조건을 만족하는 경로와 망향휴게소 fallback을 찾지 못했습니다.")
    def serialize_plan(result):
        stops=[]
        for stop in result["plan"]:
            ar=stop["available"]/max(stop["total"],1)
            stops.append({"rest_area_name":stop["name"],"distance_km":stop["km"],"truck_lounge":stop["lounge"],"arrival_soc":round(stop["arrival_soc"],1),"charge_target_soc":TARGET_SOC,"estimated_charge_minutes":round(stop["charge_minutes"],1),"estimated_arrival_time":stop["arrival_time"].isoformat(),"charger_total":stop["total"],"charger_available":stop["available"],"charger_in_use":stop["in_use"],"max_output_kw":stop["max_output_kw"],"availability_label":"매우 높음" if ar>=.7 else "높음" if ar>=.4 else "보통","charger_source":stop["source"]})
        return {"charging_stops":stops,"destination_time":result["destination_time"].isoformat() if result["destination_time"] else None,"destination_soc":round(result["destination_soc"],1) if result["destination_soc"] is not None else None,"total_charge_minutes":round(result["total_charge_minutes"],1)}
    best=serialize_plan(feasible[0])
    return {"driver_name":req.driver_name,"current_soc":req.current_soc,"safe_route_found":safe_route_found,"recommended_route":best,"alternatives":[serialize_plan(x) for x in feasible[1:4]],"metadata":{"model":MODEL_NAME,"model_inference_used":True,"model_prediction_kwh_per_100km":round(consumption,2),"safe_consumption_kwh_per_100km":round(safe_consumption,2),"correction_ratio":round(correction_ratio,4),"payload_out_of_training_range":out_of_range,"payload_extrapolation_used":out_of_range,"charger_api_ok":api_ok,"charger_status_is_current_snapshot":True,"route_total_km":ROUTE_TOTAL_KM,"safety_floor_soc":CRITICAL_SOC,"onward_distance_km":ONWARD_DISTANCE_KM,"consumption_uncertainty_pct":10,"required_destination_soc":round(required_destination_soc,1)}}
