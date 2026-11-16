# Неделя 1: как сделаны Shorts №2–5 (2026-11-16)

Серия «Kapi in the League», каждый Short = 5 клипов по 6 с, 480p, Seedance 2.0 mini (`dreamina-seedance-2-0-mini-260615`).
Тексты клипов: `plan/shortN/generate.json`, монтаж: `edit.json`, YouTube: `youtube.json`, обложка: `thumbnail.jpg`.
Референс героев: `plan/ref/kapi_ref.jpg` (Капи, Бруно, Банни), `plan/ref/rico_ref.jpg` (Рико, второй референс только для клипов с попугаем).

| № | Название | Табло | Следующая серия |
|---|----------|-------|-----------------|
| 1 | Season Opener | 0-0 → 2-0 | Bunny's Big Dunk |
| 2 | Bunny's Big Dunk | 2-0 → 2-2 | Bruno's Wall |
| 3 | Bruno's Wall | 2-2 | Rico Loses It |
| 4 | Rico Loses It | 4-6 → 6-6 | Overtime |
| 5 | Overtime | 6-6 → 9-6 | Season 1 Finale, «More Kapi soon» |

## Как собрать один Short (из папки `run/sN`, она в .gitignore)

```
mkdir -p run/s2/ref && cp plan/ref/*.jpg run/s2/ref/ && cp plan/short2/generate.json plan/short2/edit.json run/s2/
cd run/s2
python3 ../../scripts/seedance.py submit generate.json c1 c2 c3 c4 c5     # платно, ~$0.14 за клип
python3 ../../scripts/seedance.py wait c1 c2 c3 c4 c5
python3 ../../scripts/speech_times.py clips/c1.mp4 "текст реплики"        # тайминг субтитров
python3 ../../scripts/build_short.py edit.json out.mp4                    # монтаж, ~3 мин
python3 ../../scripts/mix_music.py out.mp4 ../../music/original/kapi-theme-bed.mp3 final.mp4 --music-start 0
python3 ../../scripts/make_thumbnail.py final.mp4 14.9 thumbnail.jpg "СТРОКА 1" "СТРОКА 2"
python3 ../../scripts/upload.py final.mp4 --meta ../../plan/short2/youtube.json --made-for-kids no
python3 ../../scripts/yt_status.py VIDEO_ID
```

## Что ловит фильтр BytePlus («возможное нарушение авторских прав») и что помогло

- Белый кролик Банни как главный объект в кадре (прыжки, кружение, висит, падает, обморок, ест арбуз). Помогает: общий или боковой план, Банни на заднем плане, гэг отдан другому зверю (енот в оранжевом, лиса в красном, белка в жёлтом).
- Лиса и кролик рядом в среднем плане (три отказа подряд). Енот и кролик прошли.
- Звук: крик «I can't breathe» отклонён по аудио, заменили на «Oh no!».
- Рико без референса получился красной птицей, похожей на Angry Birds. С референсом (`extra_refs` в generate.json) держится как алый ара в синих наушниках.
- Заблокированные попытки по токенам не показаны, но проверьте Billing BytePlus.
