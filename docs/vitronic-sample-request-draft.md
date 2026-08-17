# VITRONIC 샘플 출력 요청 — 이메일 초안

수신: Robin Oberlé (스캐너 조달 담당) — 또는 Waldemar 경유
목적: 장비 도착 전에 데이터 경로를 확정하기 위한 샘플 출력 확보.
포인트클라우드 전용 출력이면 surface reconstruction이 신규 작업이 되므로
가장 먼저 확인해야 할 리스크다.

---

Subject: BodyLoop sample output file for software integration

Hi Robin,

I am currently building the measurement pipeline that will consume the 3D
scanner output, so that we can swap in the real device with minimal
integration work once it arrives. To design the input adapter correctly, it
would help a lot to get the following from VITRONIC (or from the quote
documents, if already included):

1. One real sample output file of a BodyLoop scan (any anonymized subject)
2. The file format(s) of the export (e.g. OBJ/PLY/proprietary)
3. Whether the export is a closed mesh, an open mesh, or a point cloud only
4. Coordinate system and units of the export
5. Whether landmark coordinates and automatic measurements can be exported,
   and in which format
6. API/SDK documentation, if an automation interface exists

Especially point 3 decides whether we need an additional surface
reconstruction step, so an early answer on that alone would already help.

Thanks a lot!

Best regards,
Junewoo
