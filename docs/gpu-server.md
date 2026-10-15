# GPU 개인 서버 — 인코더 학습 절차

서버가 하는 일은 하나다: 합성 SMPL 몸(과 절차적 의류 셸)의 포인트클라우드에서
SMPL beta·표준화 측정벡터·임베딩을 예측하는 `PointEncoder`를 학습한다.
측정도, 사이즈 배정도, 검색도 서버에서 하지 않는다. 학습된 가중치만 이 워크스테이션으로
돌아와 ONNX로 내보내지고, 질의는 CPU에서 돈다 (`index query --encoder`).

## 0. 올리기 전 — 라이선스 (한 번만)

`docs/licenses/scope.md` **항목 1**의 "Location / jurisdiction" 칸을 채우고 커밋한다.
서버가 어디에 있는지(국가·운영 주체)가 적혀야 전송 기록이 완성된다. 그 전에는 올리지 않는다.

올라가는 것: `data/training/<이름>/` (샤드 `.npz` + `manifest.json`)만.
`scripts/export_training_set.py`가 저장소에 라이선스 제한 레코드가 하나라도 있으면 거부하므로,
샤드가 만들어졌다는 사실 자체가 합성 전용이라는 증빙이다. `manifest.json`의
`licence_classes`가 `["synthetic_smpl"]`인지 눈으로 한 번 더 확인한다.

올라가지 않는 것: `data/external/`, `data/retrieval/real-local`·`studio`, `models/smpl/`, CAPE 파생물 전부.

## 1. 서버 준비

```bash
git clone https://github.com/Juunary/body_measure.git && cd body_measure
python -m venv .venv && . .venv/bin/activate
pip install torch --index-url https://download.pytorch.org/whl/cu126   # CUDA 버전은 서버 드라이버에 맞게
pip install numpy onnxscript onnxruntime
python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
```

학습 스크립트가 쓰는 것은 `body_measure/inference/encoder.py`(torch만)와 numpy다.
trimesh·smplx·SMPL 모델 파일은 필요 없다 — 샘플링은 이쪽에서 끝났다.

## 2. 샤드 업로드

```bash
# 워크스테이션에서
scp -r data/training/syn-neutral user@server:~/body_measure/data/training/
```

두 세트가 있다. `syn-2600`(2,600명, 227 MB)은 파이프라인 확인용, `syn-neutral`(10,000명,
약 900 MB)이 본 학습용이다. 둘 다 같은 feature space(`meas-v2`)이고, 몸 1명당 몸 1 + 절차적 셸 3의
4,096점 클라우드가 float16으로 들어 있다.

## 3. 학습

```bash
cd ~/body_measure
PYTHONUTF8=1 python scripts/train_encoder.py \
  --data data/training/syn-neutral \
  --out checkpoints/encoder-syn-neutral.pt \
  --epochs 60 --batch 64 --lr 1e-3
```

- 검증은 저장소의 `holdout` split(10 %)이며 어떤 그래디언트도 보지 않는다.
- 에폭마다 `val meas loss`와 **가슴 MAE(mm)**를 찍는다. 종료 기준은 결정 #59 P4:
  합성 held-out 셸에서 가슴 SD가 C2(약 12–18 mm)보다 작거나 같아야 한다.
  CPU 스모크(200명·2에폭)는 MAE 180 mm였다 — 학습 전 수준이다.
- `--epochs 60`은 1만 명 × 4 클라우드 = 4만 샘플, GPU 한 장에서 수십 분이다.
  `syn-2600`으로 먼저 돌려 보려면 경로와 출력 이름만 바꾼다.
- 체크포인트에는 feature space와 학습 샤드의 manifest가 같이 들어간다. 그래서
  `export_encoder`가 어느 저장소의 공간에서 학습됐는지 알고, 질의 쪽이 다른 저장소를 거부할 수 있다.

## 4. 돌려받기

```bash
# 워크스테이션에서
scp user@server:~/body_measure/checkpoints/encoder-syn-neutral.pt checkpoints/
scp user@server:~/body_measure/checkpoints/encoder-syn-neutral.history.json checkpoints/
```

그다음 이쪽에서:

```powershell
$env:PYTHONUTF8=1
.venv\Scripts\python -m body_measure.inference.export_encoder checkpoints\encoder-syn-neutral.pt checkpoints\encoder-syn-neutral.onnx
.venv\Scripts\python -m body_measure index query --db syn-neutral data\generated\smpl_rand0_apose.obj --input-unit m --encoder checkpoints\encoder-syn-neutral.onnx
```

`export_encoder`는 eager 대비 parity(< 1e-4)와 dynamic batch를 확인하고 `*.export.json`에 적는다.
`.pt`·`.onnx`는 `.gitignore`에 있다. 가중치는 공개하지 않는다(`scope.md` 항목 7).

## 5. 서버 정리

학습이 끝나고 체크포인트를 받은 뒤 서버의 `data/training/`과 `checkpoints/`를 지운다
(`scope.md` 항목 1, retention). 지운 날짜를 항목 1 아래에 한 줄 적는다.

## 서버에서 하면 안 되는 것

- 실제 스캔(Texel·NOMO·HSRD)이나 CAPE 파생 데이터를 올리는 것. 두 번째 scope 항목이 먼저다.
- 서버에서 측정·사이즈 배정을 하는 것. 숫자는 이 워크스테이션의 기하 파이프라인만 낸다.
- 가중치를 다른 곳에 올리거나 공유하는 것.
