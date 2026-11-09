BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TYPE date_precision AS ENUM ('YEAR', 'MONTH', 'DAY');
CREATE TYPE verification_status AS ENUM ('VERIFIED', 'CONFIRMED', 'PRELIMINARY', 'TO_VERIFY', 'UNCERTAIN');
CREATE TYPE editorial_status AS ENUM ('NEW', 'TO_VERIFY', 'READY', 'IN_PROGRESS', 'PUBLISHED', 'DISCARDED');
CREATE TYPE event_type AS ENUM ('BIRTH', 'DEATH', 'RELEASE', 'CONCERT', 'FESTIVAL', 'RECORDING', 'BROADCAST', 'AWARD', 'CHART', 'INDUSTRY', 'OTHER');

CREATE TABLE artists (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    canonical_name TEXT NOT NULL,
    sort_name TEXT,
    artist_type TEXT NOT NULL DEFAULT 'PERSON',
    country_code CHAR(2),
    begin_year SMALLINT,
    end_year SMALLINT,
    biography TEXT,
    disambiguation TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_artist_years CHECK (begin_year IS NULL OR end_year IS NULL OR end_year >= begin_year)
);
CREATE INDEX ix_artists_name ON artists (lower(canonical_name));

CREATE TABLE artist_memberships (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    group_artist_id UUID NOT NULL REFERENCES artists(id) ON DELETE CASCADE,
    member_artist_id UUID NOT NULL REFERENCES artists(id) ON DELETE CASCADE,
    role TEXT,
    start_year SMALLINT,
    end_year SMALLINT,
    notes TEXT,
    CONSTRAINT uq_membership UNIQUE (group_artist_id, member_artist_id, role),
    CONSTRAINT ck_membership_years CHECK (start_year IS NULL OR end_year IS NULL OR end_year >= start_year),
    CONSTRAINT ck_membership_not_self CHECK (group_artist_id <> member_artist_id)
);

CREATE TABLE genres (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL UNIQUE,
    parent_genre_id UUID REFERENCES genres(id),
    description TEXT
);
CREATE TABLE artist_genres (
    artist_id UUID NOT NULL REFERENCES artists(id) ON DELETE CASCADE,
    genre_id UUID NOT NULL REFERENCES genres(id) ON DELETE CASCADE,
    confidence NUMERIC(4,3),
    PRIMARY KEY (artist_id, genre_id),
    CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1)
);

CREATE TABLE labels (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    country_code CHAR(2),
    founded_year SMALLINT,
    dissolved_year SMALLINT,
    website TEXT,
    UNIQUE (name, country_code)
);

CREATE TABLE release_groups (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title TEXT NOT NULL,
    primary_type TEXT NOT NULL,
    secondary_type TEXT,
    first_release_year SMALLINT,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_release_groups_title ON release_groups (lower(title));

CREATE TABLE releases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    release_group_id UUID REFERENCES release_groups(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    country_code CHAR(2),
    release_date DATE,
    release_year SMALLINT,
    release_month SMALLINT,
    release_day SMALLINT,
    date_precision date_precision NOT NULL DEFAULT 'YEAR',
    label_id UUID REFERENCES labels(id) ON DELETE SET NULL,
    catalog_number TEXT,
    format TEXT,
    barcode TEXT,
    status verification_status NOT NULL DEFAULT 'TO_VERIFY',
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_release_month CHECK (release_month IS NULL OR release_month BETWEEN 1 AND 12),
    CONSTRAINT ck_release_day CHECK (release_day IS NULL OR release_day BETWEEN 1 AND 31),
    CONSTRAINT ck_release_precision CHECK (
      (date_precision = 'YEAR' AND release_year IS NOT NULL AND release_month IS NULL AND release_day IS NULL) OR
      (date_precision = 'MONTH' AND release_year IS NOT NULL AND release_month IS NOT NULL AND release_day IS NULL) OR
      (date_precision = 'DAY' AND release_year IS NOT NULL AND release_month BETWEEN 1 AND 12 AND release_day BETWEEN 1 AND 31
       AND make_date(release_year::int, release_month, release_day) IS NOT NULL)
    )
);
CREATE INDEX ix_releases_date ON releases (release_year, release_month, release_day);
CREATE INDEX ix_releases_group ON releases (release_group_id);

CREATE TABLE release_artists (
    release_id UUID NOT NULL REFERENCES releases(id) ON DELETE CASCADE,
    artist_id UUID NOT NULL REFERENCES artists(id) ON DELETE CASCADE,
    credited_as TEXT,
    credit_role TEXT NOT NULL DEFAULT 'PRIMARY',
    position SMALLINT,
    PRIMARY KEY (release_id, artist_id, credit_role)
);
CREATE TABLE release_genres (
    release_id UUID NOT NULL REFERENCES releases(id) ON DELETE CASCADE,
    genre_id UUID NOT NULL REFERENCES genres(id) ON DELETE CASCADE,
    PRIMARY KEY (release_id, genre_id)
);

CREATE TABLE venues (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    city TEXT,
    region TEXT,
    country_code CHAR(2),
    latitude NUMERIC(9,6),
    longitude NUMERIC(9,6)
);

CREATE TABLE events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title TEXT NOT NULL,
    event_type event_type NOT NULL,
    description TEXT,
    event_year SMALLINT,
    event_month SMALLINT,
    event_day SMALLINT,
    date_precision date_precision NOT NULL DEFAULT 'YEAR',
    event_date DATE,
    end_date DATE,
    announcement_date DATE,
    venue_id UUID REFERENCES venues(id) ON DELETE SET NULL,
    country_code CHAR(2),
    status verification_status NOT NULL DEFAULT 'TO_VERIFY',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_event_month CHECK (event_month IS NULL OR event_month BETWEEN 1 AND 12),
    CONSTRAINT ck_event_day CHECK (event_day IS NULL OR event_day BETWEEN 1 AND 31),
    CONSTRAINT ck_event_precision CHECK (
      (date_precision = 'YEAR' AND event_year IS NOT NULL AND event_month IS NULL AND event_day IS NULL) OR
      (date_precision = 'MONTH' AND event_year IS NOT NULL AND event_month IS NOT NULL AND event_day IS NULL) OR
      (date_precision = 'DAY' AND event_year IS NOT NULL AND event_month BETWEEN 1 AND 12 AND event_day BETWEEN 1 AND 31
       AND make_date(event_year::int, event_month, event_day) IS NOT NULL)
    ),
    CONSTRAINT ck_event_range CHECK (end_date IS NULL OR event_date IS NULL OR end_date >= event_date)
);
CREATE INDEX ix_events_calendar ON events (event_month, event_day, event_year);
CREATE INDEX ix_events_type ON events (event_type);

CREATE TABLE event_artists (
    event_id UUID NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    artist_id UUID NOT NULL REFERENCES artists(id) ON DELETE CASCADE,
    role TEXT NOT NULL DEFAULT 'PARTICIPANT',
    PRIMARY KEY (event_id, artist_id, role)
);

CREATE TABLE awards (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    awarding_body TEXT,
    category TEXT,
    edition_year SMALLINT,
    event_id UUID REFERENCES events(id) ON DELETE SET NULL
);

CREATE TABLE sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    source_type TEXT NOT NULL,
    base_url TEXT,
    publisher TEXT,
    reliability_tier SMALLINT,
    license_name TEXT,
    terms_url TEXT,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (reliability_tier IS NULL OR reliability_tier BETWEEN 1 AND 5)
);

-- Una riga rappresenta una specifica affermazione documentale su una data.
CREATE TABLE date_assertions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id UUID NOT NULL REFERENCES sources(id) ON DELETE RESTRICT,
    subject_kind TEXT NOT NULL CHECK (subject_kind IN ('ARTIST_BIRTH','ARTIST_DEATH','RELEASE','EVENT')),
    artist_id UUID REFERENCES artists(id) ON DELETE CASCADE,
    release_id UUID REFERENCES releases(id) ON DELETE CASCADE,
    event_id UUID REFERENCES events(id) ON DELETE CASCADE,
    asserted_year SMALLINT,
    asserted_month SMALLINT,
    asserted_day SMALLINT,
    precision date_precision NOT NULL,
    status verification_status NOT NULL DEFAULT 'TO_VERIFY',
    evidence_url TEXT,
    evidence_note TEXT,
    retrieved_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (
      (subject_kind IN ('ARTIST_BIRTH','ARTIST_DEATH') AND artist_id IS NOT NULL AND release_id IS NULL AND event_id IS NULL) OR
      (subject_kind = 'RELEASE' AND release_id IS NOT NULL AND artist_id IS NULL AND event_id IS NULL) OR
      (subject_kind = 'EVENT' AND event_id IS NOT NULL AND artist_id IS NULL AND release_id IS NULL)
    ),
    CHECK (
      (precision = 'YEAR' AND asserted_year IS NOT NULL AND asserted_month IS NULL AND asserted_day IS NULL) OR
      (precision = 'MONTH' AND asserted_year IS NOT NULL AND asserted_month IS NOT NULL AND asserted_month BETWEEN 1 AND 12 AND asserted_day IS NULL) OR
      (precision = 'DAY' AND asserted_year IS NOT NULL AND asserted_month IS NOT NULL AND asserted_month BETWEEN 1 AND 12
       AND asserted_day IS NOT NULL AND asserted_day BETWEEN 1 AND 31
       AND make_date(asserted_year::int, asserted_month, asserted_day) IS NOT NULL)
    )
);
CREATE INDEX ix_date_assertions_artist ON date_assertions (artist_id);
CREATE INDEX ix_date_assertions_release ON date_assertions (release_id);
CREATE INDEX ix_date_assertions_event ON date_assertions (event_id);

-- Collegamento documentale delle entità non limitato alle sole date.
CREATE TABLE entity_sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id UUID NOT NULL REFERENCES sources(id) ON DELETE RESTRICT,
    artist_id UUID REFERENCES artists(id) ON DELETE CASCADE,
    release_id UUID REFERENCES releases(id) ON DELETE CASCADE,
    event_id UUID REFERENCES events(id) ON DELETE CASCADE,
    evidence_url TEXT,
    evidence_note TEXT,
    status verification_status NOT NULL DEFAULT 'TO_VERIFY',
    retrieved_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (num_nonnulls(artist_id, release_id, event_id) = 1)
);

CREATE TABLE external_identifiers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    namespace TEXT NOT NULL,
    identifier TEXT NOT NULL,
    artist_id UUID REFERENCES artists(id) ON DELETE CASCADE,
    release_group_id UUID REFERENCES release_groups(id) ON DELETE CASCADE,
    release_id UUID REFERENCES releases(id) ON DELETE CASCADE,
    event_id UUID REFERENCES events(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (num_nonnulls(artist_id, release_group_id, release_id, event_id) = 1),
    UNIQUE (namespace, identifier)
);

CREATE TABLE editorial_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title TEXT NOT NULL,
    summary TEXT,
    status editorial_status NOT NULL DEFAULT 'NEW',
    priority_score NUMERIC(5,2),
    assigned_at TIMESTAMPTZ,
    published_at TIMESTAMPTZ,
    article_url TEXT,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (priority_score IS NULL OR priority_score BETWEEN 0 AND 100)
);
CREATE TABLE editorial_item_events (
    editorial_item_id UUID NOT NULL REFERENCES editorial_items(id) ON DELETE CASCADE,
    event_id UUID NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    PRIMARY KEY (editorial_item_id, event_id)
);
CREATE TABLE editorial_item_releases (
    editorial_item_id UUID NOT NULL REFERENCES editorial_items(id) ON DELETE CASCADE,
    release_id UUID NOT NULL REFERENCES releases(id) ON DELETE CASCADE,
    PRIMARY KEY (editorial_item_id, release_id)
);
CREATE TABLE editorial_item_artists (
    editorial_item_id UUID NOT NULL REFERENCES editorial_items(id) ON DELETE CASCADE,
    artist_id UUID NOT NULL REFERENCES artists(id) ON DELETE CASCADE,
    PRIMARY KEY (editorial_item_id, artist_id)
);
CREATE TABLE editorial_scores (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    editorial_item_id UUID NOT NULL REFERENCES editorial_items(id) ON DELETE CASCADE,
    historical_importance NUMERIC(5,2) NOT NULL DEFAULT 0,
    artist_relevance NUMERIC(5,2) NOT NULL DEFAULT 0,
    cultural_influence NUMERIC(5,2) NOT NULL DEFAULT 0,
    discographic_interest NUMERIC(5,2) NOT NULL DEFAULT 0,
    source_availability NUMERIC(5,2) NOT NULL DEFAULT 0,
    narrative_potential NUMERIC(5,2) NOT NULL DEFAULT 0,
    total_score NUMERIC(5,2) NOT NULL DEFAULT 0,
    scoring_version TEXT NOT NULL DEFAULT 'v1',
    scored_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (historical_importance BETWEEN 0 AND 25),
    CHECK (artist_relevance BETWEEN 0 AND 20),
    CHECK (cultural_influence BETWEEN 0 AND 20),
    CHECK (discographic_interest BETWEEN 0 AND 15),
    CHECK (source_availability BETWEEN 0 AND 10),
    CHECK (narrative_potential BETWEEN 0 AND 10),
    CHECK (total_score BETWEEN 0 AND 100)
);
CREATE TABLE editorial_tags (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL UNIQUE
);
CREATE TABLE editorial_item_tags (
    editorial_item_id UUID NOT NULL REFERENCES editorial_items(id) ON DELETE CASCADE,
    editorial_tag_id UUID NOT NULL REFERENCES editorial_tags(id) ON DELETE CASCADE,
    PRIMARY KEY (editorial_item_id, editorial_tag_id)
);

CREATE TABLE ingestion_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id UUID REFERENCES sources(id) ON DELETE SET NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'RUNNING',
    records_seen INTEGER NOT NULL DEFAULT 0,
    records_imported INTEGER NOT NULL DEFAULT 0,
    records_rejected INTEGER NOT NULL DEFAULT 0,
    error_summary TEXT
);
CREATE TABLE raw_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ingestion_run_id UUID NOT NULL REFERENCES ingestion_runs(id) ON DELETE CASCADE,
    source_record_id TEXT,
    payload JSONB NOT NULL,
    payload_hash TEXT,
    processing_status TEXT NOT NULL DEFAULT 'PENDING',
    received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed_at TIMESTAMPTZ
);
CREATE INDEX ix_raw_records_run ON raw_records (ingestion_run_id);
CREATE INDEX ix_raw_records_payload_gin ON raw_records USING GIN (payload);

COMMIT;
