# 전기 화물차 운행 최적화 서비스

봉고 EV 1톤의 현재 SOC, 적재 중량, 출발 시간을 바탕으로 고정 노선의 충전·휴식 지점과 도착 시간을 추천하는 프론트엔드 MVP입니다.

## 실행

```bash
# 터미널 1
.venv\Scripts\python -m uvicorn backend.app.main:app --port 8000

# 터미널 2
pnpm dev
```

## 현재 계산 범위

- 봉고 EV 기준 배터리 60.4kWh, 고속도로 전비 2.7km/kWh
- Notebook과 동일 조건으로 검증된 XGBoost 추론 및 봉고 EV 상대 보정
- 적재량 0~1,000kg을 모델에 직접 입력하되 500kg 초과 외삽 경고
- 제공된 안성→칠곡 휴게소 구간 202km를 서비스 전체 노선으로 가정
- 모든 충전소 부분집합을 탐색하는 다회 충전 계획
- 목적지 안전 바닥 10%, IC 이후 10km 주행에너지, 소비량 불확실성 10% 반영
- 평균 속도 80km/h 기반 ETA
- 환경부 `EvCharger/getChargerInfo` 현재 상태 조회
- API 오류 또는 매칭 데이터 부재 시 명시적인 fallback snapshot
- 안전 경로가 없으면 망향휴게소 fallback을 반환하되 안전 경로가 아님을 표시

원본 `ev_best_model.pkl`은 보존합니다. 해당 파일은 저장 환경의 한글 feature 직렬화 문제로 현재 런타임에서 비정상 예측을 반환해, Notebook의 동일 데이터 split과 하이퍼파라미터로 `ev_best_model_compatible.pkl`을 재현해 사용합니다. 재현 모델의 테스트 성능은 R² 0.9472, MAE 0.6678, RMSE 0.8451입니다.
