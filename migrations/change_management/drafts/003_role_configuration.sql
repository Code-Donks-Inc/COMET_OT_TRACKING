-- ============================================================
-- MIGRATION 003 - DATABASE ROLE CONFIGURATION
-- ============================================================
--
-- Document status: IN DEVELOPMENT
-- Security review status: OPEN
-- Deployment status: NOT APPLIED
--
-- Purpose:
-- Define proposed least-privilege PostgreSQL roles and
-- permissions for the OT Asset Intelligence application.
--
-- Supporting design:
-- migrations/change_management/reviews/003_role_design.txt
--
-- Supporting security requirements:
-- migrations/change_management/reviews/003_policy_requirements.txt
--
-- DEPLOYMENT RESTRICTIONS
--
-- This file is a development draft.
-- Do not execute against the existing database.
-- Do not modify existing database roles or permissions.
-- Do not enable asset assignment approval or rejection.
--
-- Role ownership, trusted authentication, client authorization,
-- and permission testing must be completed before deployment.
--
-- Migration 003 remains IN DEVELOPMENT - NOT APPLIED.
-- ============================================================

-- ============================================================
-- ROLE 001 - RESTRICTED APPLICATION RUNTIME
-- ============================================================
--
-- Proposed role: otintel_app
--
-- Purpose:
-- Provide a dedicated PostgreSQL login for ordinary
-- application operations without administrative privileges.
--
-- This role must not own protected database objects or
-- directly approve asset assignment requests.
--
-- DEVELOPMENT DRAFT - DO NOT EXECUTE

CREATE ROLE otintel_app
    WITH
    LOGIN
    NOSUPERUSER
    NOCREATEDB
    NOCREATEROLE
    NOREPLICATION
    NOBYPASSRLS
    NOINHERIT;

-- ============================================================
-- ROLE 001 - SCHEMA ACCESS
-- ============================================================
--
-- Permit access to explicitly authorized objects in public.
-- USAGE does not grant permission to read or modify tables.
-- CREATE must not be granted to the application runtime role.
--
-- DEVELOPMENT DRAFT - DO NOT EXECUTE

GRANT USAGE ON SCHEMA public TO otintel_app;

-- ============================================================
-- ROLE 001 - CLIENT TABLE ACCESS
-- ============================================================
--
-- Allow the application to read client records.
-- Do not permit the runtime role to create, modify,
-- or delete client records.
--
-- IMPORTANT:
-- This grant does not enforce client-level authorization.
-- Authentication and client-scoped access controls are
-- required before production deployment.
--
-- DEVELOPMENT DRAFT - DO NOT EXECUTE

GRANT SELECT ON TABLE public.clients TO otintel_app;

-- ============================================================
-- ROLE 001 - ASSET TABLE ACCESS
-- ============================================================
--
-- Allow asset inventory reads and restricted asset creation.
-- Do not grant direct UPDATE or DELETE permissions.
--
-- Exclude cabinet_id from permitted INSERT columns to
-- prevent ordinary application operations from assigning
-- cabinets during asset creation.
--
-- IMPORTANT:
-- Column restrictions alone do not enforce client isolation.
-- Existing object privileges, role memberships, and other
-- database write paths must also be reviewed.
--
-- DEVELOPMENT DRAFT - DO NOT EXECUTE

GRANT SELECT ON TABLE public.assets TO otintel_app;

GRANT INSERT (
    client_id,
    asset_tag,
    vendor,
    product,
    model,
    version,
    criticality
)
ON TABLE public.assets TO otintel_app;

-- ============================================================
-- ROLE 001 - SITE TABLE ACCESS
-- ============================================================
--
-- Allow site inventory reads and restricted site creation.
-- Do not grant UPDATE or DELETE permissions.
--
-- IMPORTANT:
-- These grants do not enforce client-level authorization.
-- Tenant isolation must be implemented and tested before
-- production deployment.
--
-- DEVELOPMENT DRAFT - DO NOT EXECUTE

GRANT SELECT ON TABLE public.sites TO otintel_app;

GRANT INSERT (
    client_id,
    name
)
ON TABLE public.sites TO otintel_app;

-- ============================================================
-- ROLE 001 - BUILDING TABLE ACCESS
-- ============================================================
--
-- Allow building inventory reads and restricted creation.
-- Do not grant UPDATE or DELETE permissions.
--
-- IMPORTANT:
-- These grants do not enforce client-level authorization.
-- Tenant isolation must be implemented and tested before
-- production deployment.
--
-- DEVELOPMENT DRAFT - DO NOT EXECUTE

GRANT SELECT ON TABLE public.buildings TO otintel_app;

GRANT INSERT (
    client_id,
    site_id,
    name
)
ON TABLE public.buildings TO otintel_app;

-- ============================================================
-- ROLE 001 - CABINET TABLE ACCESS
-- ============================================================
--
-- Allow cabinet inventory reads and restricted creation.
-- Do not grant UPDATE or DELETE permissions.
--
-- IMPORTANT:
-- These grants do not enforce client-level authorization.
-- Tenant isolation must be implemented and tested before
-- production deployment.
--
-- DEVELOPMENT DRAFT - DO NOT EXECUTE

GRANT SELECT ON TABLE public.cabinets TO otintel_app;

GRANT INSERT (
    client_id,
    building_id,
    name
)
ON TABLE public.cabinets TO otintel_app;

-- ============================================================
-- ROLE 006 - RESTRICTED BACKUP WORKER
-- ============================================================
--
-- Proposed role: otintel_backup_worker
-- Purpose: Execute authorized background backup operations.
--
-- This role is separate from the ordinary application role.
-- Backup table permissions will be defined after reviewing
-- the complete worker authorization requirements.
--
-- DEVELOPMENT DRAFT - DO NOT EXECUTE

CREATE ROLE otintel_backup_worker
    WITH
    LOGIN
    NOSUPERUSER
    NOCREATEDB
    NOCREATEROLE
    NOREPLICATION
    NOBYPASSRLS
    NOINHERIT;
