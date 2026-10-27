-- Test 002: Client isolation
-- All database changes must be rolled back.
-- Do not execute until the test is complete and reviewed.

BEGIN;

-- Migration 002 will be inserted into the test transaction
-- without its BEGIN or COMMIT statements.
-- Do not execute this file yet.

-- Temporary test records will be added below.

-- Create a temporary second client and its location hierarchy.
-- These records must never be committed.

INSERT INTO public.clients (name)
VALUES ('Migration 002 Isolation Test Client');

INSERT INTO public.sites (client_id, name)
SELECT id, 'Test Site'
FROM public.clients
WHERE name = 'Migration 002 Isolation Test Client';

INSERT INTO public.buildings (site_id, client_id, name)
SELECT s.id, s.client_id, 'Test Building'
FROM public.sites s
JOIN public.clients c ON c.id = s.client_id
WHERE c.name = 'Migration 002 Isolation Test Client';

INSERT INTO public.cabinets (building_id, client_id, name)
SELECT b.id, b.client_id, 'Test Cabinet'
FROM public.buildings b
JOIN public.clients c ON c.id = b.client_id
WHERE c.name = 'Migration 002 Isolation Test Client';

-- Verify that cross-client cabinet assignments are rejected.
-- A rejected assignment must not change the existing asset.

DO $$
DECLARE
    test_cabinet_id INTEGER;
    test_asset_id INTEGER;
BEGIN
    SELECT cab.id INTO STRICT test_cabinet_id
    FROM public.cabinets cab
    JOIN public.clients c ON c.id = cab.client_id
    WHERE c.name = 'Migration 002 Isolation Test Client';

    SELECT id INTO STRICT test_asset_id
    FROM public.assets
    WHERE client_id = 1
    ORDER BY id
    LIMIT 1;

    BEGIN
        UPDATE public.assets
        SET cabinet_id = test_cabinet_id
        WHERE id = test_asset_id;

        RAISE EXCEPTION
            'FAIL: cross-client assignment was incorrectly allowed';

    EXCEPTION
        WHEN foreign_key_violation THEN
            RAISE NOTICE
                'PASS: PostgreSQL rejected the cross-client assignment';
        WHEN OTHERS THEN
            RAISE;

    END;
END;
$$;

ROLLBACK;