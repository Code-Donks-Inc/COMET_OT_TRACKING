--Migration 001: Physical asset location hierarchy
--Client > Site > Building > Asset
--
-- Additive Migration. Existing clients and assets are preserved
-- Do not execute until the migration has been reviewed.

BEGIN;
--sites belong to clients
CREATE TABLE public.sites(
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    client_id INTEGER NOT NULL
        REFERENCES public.clients(id),
    name VARCHAR(200) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT sites_client_name_unique
        UNIQUE (client_id, name)
);
-- buildings belong to sites
CREATE TABLE public.buildings(
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    site_id INTEGER NOT NULL
        REFERENCES public.sites(id),
    name VARCHAR(200) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT building_site_name_unique
        UNIQUE (site_id, name)
);

--cabinets belong to buildings.
CREATE TABLE public.cabinets (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    building_id INTEGER NOT NULL
        REFERENCES public.buildings(id),
    name VARCHAR(200) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT cabinets_building_name_unique
        UNIQUE (building_id, name)
);

COMMIT;