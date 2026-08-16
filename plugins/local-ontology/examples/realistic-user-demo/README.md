# Realistic synthetic user demo

This fixture models one fictional Korean knowledge worker, **Kim Yunseo**, over a
three-week period. Yunseo combines quantitative research, personal software
development, math tutoring, and audio-tool exploration.

The themes were generalized from recurring categories in local notes and AI
coding-assistant logs supplied by the repository owner. No raw conversation,
credential, account identifier, real person name, private location, or absolute
local path was copied into this fixture. Names, places, URLs, dates, wording, and
event combinations are synthetic.

## Included source shapes

- `chromium-history.sql`: eight browser pages and ten visits in the exact
  Chromium schema supported by the importer. One explicitly fake private page is
  present so the exclusion pattern can be demonstrated.
- `codex-logs/`: four deterministic Markdown conversations containing topics,
  decisions, and plans.
- `google-maps-takeout/`: three fictional saved places in the supported Google
  Maps Takeout GeoJSON layout.
- `graph-overlay.json`: explicit, evidenced links between facts extracted from
  the three sources, plus policy-boundary records.
- `policy.json`: the model-facing `work` world policy.

## Story and useful anchors

| Anchor | What it demonstrates |
| --- | --- |
| `챗봇 분석` | A research topic connected to a metrics decision, analysis conversation, browser documentation, and a fictional meeting place. |
| `내 기억 시스템` | A local-ontology project connected to SQLite research, its design conversation, and a fictional work lounge. |
| `수학 수업 준비` | A tutoring topic connected to a graphing tool and lesson-design conversation. |
| `오디오 믹서` | An audio project connected to WASAPI research, a design conversation, and a fictional rehearsal room. |

Build the fixture from the repository root:

```text
python plugins/local-ontology/scripts/build_realistic_demo.py --session-dir demo-output/realistic-user
```

The command prints the import report and two ready-to-present, provenance-bearing
two-hop query results, and also writes them to `demo-result.json`. For this
repository's checked-in demonstration, the generated databases, session manifest,
audit log, and result JSON live under `demo-output/realistic-user/`.
