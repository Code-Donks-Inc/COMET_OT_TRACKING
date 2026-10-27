-- Migration 002: Optional asset-to-cabinet relationship
--
-- Existing assets remain valid without a cabinet assignment.
-- Existing client_id and asset_tag fields are preserved.
--
-- Do not execute until reviewed and tested.

BEGIN;

--explicit client ownership for buildings.
-- The client must match the building's parent site.

ALTER TABLE public.sites
    ADD CONSTRAINT sites_id_client_id_unique
    UNIQUE (id,client_id);

ALTER TABLE public.buildings
    ADD COLUMN client_id INTEGER NOT NULL;

ALTER TABLE public.buildings
    ADD CONSTRAINT buildings_site_client_fkey
    FOREIGN KEY (site_id, client_id)
    REFERENCES public.sites (id, client_id);

ALTER TABLE public.buildings
    ADD CONSTRAINT buildings_id_client_id_unique
    UNIQUE (id, client_id);

-- explicit client ownership for cabinets.
-- The client must match the cabinets parent building

ALTER TABLE public.cabinets
    ADD COLUMN client_id INTEGER NOT NULL;

ALTER TABLE public.cabinets
    ADD CONSTRAINT cabinets_building_client_fkey
    FOREIGN KEY (building_id, client_id)
    REFERENCES public.buildings (id, client_id);

ALTER TABLE public.cabinets
    ADD CONSTRAINT cabinets_id_client_id_unique
    UNIQUE (id, client_id);

ALTER TABLE public.assets
    ADD COLUMN cabinet_id INTEGER;

-- Enforce matching client ownership between assets and cabinets
-- Unassigned assets remain valid because cabinet_id is nullable.

ALTER TABLE public.assets
    ADD CONSTRAINT assets_cabinet_client_fkey
    FOREIGN KEY (cabinet_id, client_id)
    REFERENCES public.cabinets(id, client_id);

CREATE INDEX assets_cabinet_id_idx
    ON public.assets (cabinet_id);

COMMIT;