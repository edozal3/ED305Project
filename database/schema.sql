DROP TABLE IF EXISTS monthly_visit;
DROP TABLE IF EXISTS park;
DROP TABLE IF EXISTS region;

CREATE TABLE region (
    region_id TEXT PRIMARY KEY,
    region_name TEXT NOT NULL,
    description TEXT
);

CREATE TABLE park (
    park_code TEXT PRIMARY KEY,
    park_name TEXT NOT NULL,
    state TEXT NOT NULL,
    designation TEXT NOT NULL,
    region_id TEXT,
    latitude REAL,
    longitude REAL,
    description TEXT,
    website TEXT,
    boundary TEXT,
    FOREIGN KEY (region_id) REFERENCES region(region_id)
);

CREATE TABLE monthly_visit (
    park_code TEXT NOT NULL,
    year INTEGER NOT NULL,
    month INTEGER NOT NULL,
    recreation_visits INTEGER,
    non_recreation_visits INTEGER,
    total_visits INTEGER,
    concessioner_lodging INTEGER,
    concessioner_camping INTEGER,
    tent_campers INTEGER,
    rv_campers INTEGER,
    backcountry INTEGER,
    nonrecreation_overnight_stays INTEGER,
    miscellaneous_overnight_stays INTEGER,
    PRIMARY KEY (park_code, year, month),
    FOREIGN KEY (park_code) REFERENCES park(park_code)
);
