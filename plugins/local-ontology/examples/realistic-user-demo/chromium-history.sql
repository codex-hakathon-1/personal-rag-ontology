CREATE TABLE urls (
  id INTEGER PRIMARY KEY,
  url TEXT NOT NULL,
  title TEXT NOT NULL,
  visit_count INTEGER NOT NULL,
  last_visit_time INTEGER NOT NULL
);

CREATE TABLE visits (
  id INTEGER PRIMARY KEY,
  url INTEGER NOT NULL,
  visit_time INTEGER NOT NULL
);

INSERT INTO urls (id, url, title, visit_count, last_visit_time) VALUES
  (1, 'https://pandas.pydata.org/docs/reference/api/pandas.DataFrame.merge.html', 'pandas DataFrame.merge documentation', 2, 13429781100000000),
  (2, 'https://www.statsmodels.org/stable/mixed_linear.html', 'Statsmodels linear mixed effects models', 1, 13429776600000000),
  (3, 'https://www.geogebra.org/graphing', 'GeoGebra graphing calculator', 1, 13430279700000000),
  (4, 'https://learn.microsoft.com/en-us/samples/microsoft/windows-classic-samples/applicationloopbackaudio-sample/', 'Application Loopback Audio sample', 1, 13430906700000000),
  (5, 'https://developer.mozilla.org/en-US/docs/Web/API/Web_Audio_API', 'Web Audio API documentation', 1, 13430547600000000),
  (6, 'https://www.sqlite.org/lang_with.html', 'SQLite WITH and recursive CTE documentation', 2, 13431323400000000),
  (7, 'https://docs.python.org/3/library/sqlite3.html', 'Python sqlite3 DB-API documentation', 2, 13431326700000000),
  (8, 'https://mail.example.invalid/inbox?token=demo-only-not-a-secret', 'Demo private inbox', 1, 13431321300000000);

INSERT INTO visits (id, url, visit_time) VALUES
  (101, 1, 13429776600000000),
  (102, 1, 13429781100000000),
  (201, 2, 13429678200000000),
  (301, 3, 13430279700000000),
  (401, 4, 13430906700000000),
  (501, 5, 13430547600000000),
  (601, 6, 13431321300000000),
  (602, 6, 13431323400000000),
  (701, 7, 13431323400000000),
  (702, 7, 13431326700000000),
  (801, 8, 13431321300000000);
