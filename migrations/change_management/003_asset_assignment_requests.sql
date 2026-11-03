---------------- NOTICE FOR ALL USERS -------------------------------
-- MIGRATION 003 SUPPORTING DOCUMENTATION
--
-- Security findings and remediation status:
-- migrations/change_management/reviews/003_security_review.txt
--
-- Security policies and implementation requirements:
-- migrations/change_management/reviews/003_policy_requirements.txt
--
-- Approval, rejection, revision, and audit workflows:
-- migrations/change_management/reviews/003_approval_workflow.txt
--
-- Document status: IN DEVELOPMENT
-- Security review status: OPEN
-- Migration status: IN DEVELOPMENT - NOT APPLIED
--
-- Assignment decisions must remain disabled until all required
-- security controls, authorization checks, and transaction
-- validation have been implemented, tested, and approved.

-- Support client-isolated foreign keys for asset assignment requests.

ALTER TABLE public.assets
    ADD CONSTRAINT assets_id_client_id_key
    UNIQUE (id, client_id);

CREATE TABLE IF NOT EXISTS public.asset_assignment_requests(
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    client_id INTEGER NOT NULL,
    asset_id INTEGER NOT NULL,
    proposed_cabinet_id INTEGER NOT null,

    original_cabinet_id INTEGER,

    requested_by VARCHAR(200) NOT NULL,
    justification TEXT NOT NULL
    CHECK (length(btrim(justification)) > 0),
    requested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT asset_assignment_requests_requested_by_check
        CHECK (BTRIM(requested_by) <> ''),

    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    reviewed_by VARCHAR(200),
    reviewed_at TIMESTAMPTZ,

    CONSTRAINT asset_assignment_requests_id_client_key
        UNIQUE (id, client_id),

    CONSTRAINT asset_assignment_requests_status_check
        CHECK (status IN ('pending', 'approved', 'rejected')),

    CONSTRAINT asset_assignment_requests_review_check
        CHECK (
            (
                status = 'pending'
                AND reviewed_by IS NULL
                AND reviewed_at IS NULL
            )
            OR
            (
                status IN ('approved', 'rejected')
                AND reviewed_by IS NOT NULL
                AND BTRIM(reviewed_by) <> ''
                AND reviewed_at IS NOT NULL
                AND reviewed_by <> requested_by
            )
        )
);

-- Require every new assignment request to begin as pending.
CREATE OR REPLACE FUNCTION public.require_pending_assignment_request()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.status <> 'pending' THEN
        RAISE EXCEPTION
            'New asset assignment requests must have pending status.';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER asset_assignment_requires_initial_status
BEFORE INSERT
ON public.asset_assignment_requests
FOR EACH ROW
EXECUTE FUNCTION public.require_pending_assignment_request();


ALTER TABLE public.asset_assignment_requests
    ADD CONSTRAINT asset_assignment_requests_client_fk
        FOREIGN KEY (client_id)
        REFERENCES public.clients (id),

    ADD CONSTRAINT asset_assignment_requests_asset_fk
        FOREIGN KEY (asset_id, client_id)
        REFERENCES public.assets (id, client_id),

    ADD CONSTRAINT asset_assignment_requests_cabinet_fk
        FOREIGN KEY (proposed_cabinet_id, client_id)
        REFERENCES public.cabinets (id, client_id),

    ADD CONSTRAINT asset_assignment_requests_original_cabinet_fk
        FOREIGN KEY (original_cabinet_id, client_id)
            REFERENCES public.cabinets (id, client_id);

-- Audit Event Table
CREATE TABLE public.asset_assignment_events(
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    request_id INTEGER NOT NULL
        REFERENCES public.asset_assignment_requests(id),

    event_type VARCHAR(30) NOT NULL,

    performed_by VARCHAR(200) NOT NULL,
    performed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT asset_assignment_events_performed_by_check
        CHECK (BTRIM(performed_by) <> ''),

    notes TEXT,

    CONSTRAINT asset_assignment_events_request_type_key
        UNIQUE (request_id, event_type),

    CONSTRAINT asset_assignment_events_type_check
        CHECK (
            event_type IN (
                'submitted',
                'approved',
                'rejected'
            )
        )
);

-- Allow only one decision event per assignment request.
CREATE UNIQUE INDEX asset_assignment_events_unique_decision
ON public.asset_assignment_events (request_id)
WHERE event_type IN ('approved', 'rejected');

-- Prevent existing audit events from being modified or deleted.
CREATE OR REPLACE FUNCTION public.prevent_assignment_event_changes()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION
        'Asset assignment audit events cannot be updated or deleted.';
END;
$$;

-- Enforce append-only behavior for asset assignment audit events.
CREATE TRIGGER asset_assignment_events_append_only
BEFORE UPDATE OR DELETE
ON public.asset_assignment_events
FOR EACH ROW
EXECUTE FUNCTION public.prevent_assignment_event_changes();

-- Preserve the original details of submitted assignment requests.
CREATE OR REPLACE FUNCTION public.protect_assignment_request_details()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.client_id IS DISTINCT FROM NEW.client_id
        OR OLD.asset_id IS DISTINCT FROM NEW.asset_id
        OR OLD.proposed_cabinet_id IS DISTINCT FROM NEW.proposed_cabinet_id
        OR OLD.original_cabinet_id IS DISTINCT FROM NEW.original_cabinet_id
        OR OLD.requested_by IS DISTINCT FROM NEW.requested_by
        OR OLD.justification IS DISTINCT FROM NEW.justification
        OR OLD.requested_at IS DISTINCT FROM NEW.requested_at
    THEN
        RAISE EXCEPTION
            'Submitted asset assignment request details cannot be modified.';
    END IF;

    -- Preserve reviewer identity and timestamp after a decision.
    IF OLD.status IN ('approved', 'rejected')
        AND (
            OLD.reviewed_by IS DISTINCT FROM NEW.reviewed_by
            OR OLD.reviewed_at IS DISTINCT FROM NEW.reviewed_at
        )
    THEN
        RAISE EXCEPTION
            'Completed assignment request details cannot be modified';
    END IF;

    RETURN NEW;
END;
$$;

-- Protect submitted assignment request details from modification.
CREATE TRIGGER asset_assignment_requests_protect_details
BEFORE UPDATE
ON public.asset_assignment_requests
FOR EACH ROW
EXECUTE FUNCTION public.protect_assignment_request_details();

-- Prevent deletion of submitted asset assignment requests.
CREATE OR REPLACE FUNCTION public.prevent_assignment_request_deletion()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION
        'Submitted asset assignment requests cannot be deleted.';
END;
$$;

-- Enforce preservation of assignment requests.
CREATE TRIGGER asset_assignment_requests_no_delete
BEFORE DELETE
ON public.asset_assignment_requests
FOR EACH ROW
EXECUTE FUNCTION public.prevent_assignment_request_deletion();

-- Restrict assignment request status transitions.
CREATE OR REPLACE FUNCTION public.validate_assignment_request_status()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.status IS DISTINCT FROM NEW.status THEN
        IF OLD.status <> 'pending'
            OR NEW.status NOT IN ('approved', 'rejected')
        THEN
            RAISE EXCEPTION
                'Invalid asset assignment request status transition: % to %',
                OLD.status,
                NEW.status;
        END IF;
    END IF;

    RETURN NEW;
END;
$$;

-- Enforce valid assignment request status transitions.
CREATE TRIGGER asset_assignment_requests_validate_status
BEFORE UPDATE OF status
ON public.asset_assignment_requests
FOR EACH ROW
EXECUTE FUNCTION public.validate_assignment_request_status();

-- Preserve historical asset cabinet assignment changes.
CREATE TABLE public.asset_assignment_revisions (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    request_id INTEGER NOT NULL UNIQUE,

    client_id INTEGER NOT NULL,
    asset_id INTEGER NOT NULL,

    previous_cabinet_id INTEGER,
    new_cabinet_id INTEGER NOT NULL,

    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT asset_assignment_revisions_request_fk
        FOREIGN KEY (request_id, client_id)
        REFERENCES public.asset_assignment_requests (id, client_id),

    CONSTRAINT asset_assignment_revisions_asset_fk
        FOREIGN KEY (asset_id, client_id)
        REFERENCES public.assets (id, client_id),

    CONSTRAINT asset_assignment_revisions_previous_cabinet_fk
        FOREIGN KEY (previous_cabinet_id, client_id)
        REFERENCES public.cabinets (id, client_id),

    CONSTRAINT asset_assignment_revisions_new_cabinet_fk
        FOREIGN KEY (new_cabinet_id, client_id)
        REFERENCES public.cabinets (id, client_id)
);

-- Prevent modification or deletion of asset assignment revision.
CREATE OR REPLACE FUNCTION public.prevent_assignment_revision_changes()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION
       'Asset assignment revisions cannot be updated or deleted.';
END;
$$;

-- Enforce append-only revision history.
CREATE TRIGGER asset_assignment_revisions_append_only
BEFORE UPDATE OR DELETE
ON public.asset_assignment_revisions
FOR EACH ROW
EXECUTE FUNCTION public.prevent_assignment_revision_changes();

-- Validate the approval request before recording a revision.
CREATE OR REPLACE FUNCTION public.validate_assignment_revision()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    approved_request public.asset_assignment_requests%ROWTYPE;
BEGIN
    SELECT *
    INTO approved_request
    FROM public.asset_assignment_requests
    WHERE id = NEW.request_id
      AND client_id = NEW.client_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'Assignment revision must reference a valid request.';
    END IF;

    IF approved_request.status <> 'approved' THEN
        RAISE EXCEPTION
            'Assignment revisions require an approved request.';
    END IF;

    IF NEW.asset_id IS DISTINCT FROM approved_request.asset_id
        OR NEW.previous_cabinet_id IS DISTINCT FROM approved_request.original_cabinet_id
        OR NEW.new_cabinet_id IS DISTINCT FROM approved_request.proposed_cabinet_id
    THEN
        RAISE EXCEPTION
            'Assignment revision does not match the approved request.';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER asset_assignment_revisions_validate
BEFORE INSERT ON public.asset_assignment_revisions
FOR EACH ROW
EXECUTE FUNCTION public.validate_assignment_revision();

-- Controlled asset assignment decision function
-- Implementation is intentionally disabled until authorization
-- And transaction validation are complete.

CREATE OR REPLACE FUNCTION public.decide_asset_assignment(
    p_request_id INTEGER,
    p_decision VARCHAR(20)
)
RETURNS VOID
LANGUAGE plpgsql
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
    assignment_request public.asset_assignment_requests%ROWTYPE;
    affected_asset public.assets%ROWTYPE;
BEGIN
    IF p_request_id IS NULL OR p_request_id <= 0 THEN
        RAISE EXCEPTION
            'Invalid asset assignment request ID: %', p_request_id;
    END IF;

    IF p_decision IS NULL
        OR p_decision NOT IN ('approved', 'rejected')
    THEN
        RAISE EXCEPTION
            'Invalid assignment decision: %', p_decision;
    END IF;

    -- Retrieve and lock the assignment request.
    SELECT *
    INTO assignment_request
    FROM public.asset_assignment_requests
    WHERE id = p_request_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'Asset assignment request % does not exist.', p_request_id;
    END IF;

    -- Only pending requests may receive a decision.
    IF assignment_request.status <> 'pending' THEN
        RAISE EXCEPTION
            'Asset assignment request % is not pending.', p_request_id;
    END IF;

    -- Retrieve and lock the affected asset.
    SELECT *
    INTO affected_asset
    FROM public.assets
    WHERE id = assignment_request.asset_id
      AND client_id = assignment_request.client_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'Asset % does not exist for client %',
            assignment_request.asset_id,
            assignment_request.client_id;
    END IF;

    -- Reject requests if the asset's cabinet has changed.
    IF affected_asset.cabinet_id
        IS DISTINCT FROM assignment_request.original_cabinet_id
    THEN
        RAISE EXCEPTION
            'Asset % cabinet assignment has changed since request %',
            assignment_request.asset_id,
            p_request_id;
    END IF;

    -- Verify the proposed cabinet belongs to the request's client.
    PERFORM 1
    FROM public.cabinets
    WHERE id = assignment_request.proposed_cabinet_id
        AND client_id = assignment_request.client_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'Proposed cabinet % does not exist for client %.',
            assignment_request.proposed_cabinet_id,
            assignment_request.client_id;
    END IF;

    RAISE EXCEPTION
        'Asset assignment decisions are not yet enabled';
END;
$$;

-- Deny default public execution of the approval function.
REVOKE ALL ON FUNCTION public.decide_asset_assignment(
    INTEGER,
    VARCHAR
) FROM PUBLIC;
