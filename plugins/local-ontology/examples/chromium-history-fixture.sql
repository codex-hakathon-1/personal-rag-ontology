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
  (1, 'https://platform.openai.com/docs/guides', 'OpenAI API guides', 2, 13398607800000000),
  (2, 'https://travel.example.org/kyoto-itinerary', 'Kyoto itinerary', 1, 13398696000000000),
  (3, 'https://bank.example.com/account?token=fixture-secret', 'Bank account', 1, 13398786000000000);

INSERT INTO visits (id, url, visit_time) VALUES
  (101, 1, 13398516000000000),
  (102, 1, 13398607800000000),
  (201, 2, 13398696000000000),
  (301, 3, 13398786000000000);
