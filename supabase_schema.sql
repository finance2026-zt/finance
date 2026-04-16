-- ═══════════════════════════════════════════════════════════════════════════
-- MicroFinance Loan Management System — Supabase / PostgreSQL Schema
-- Run this in: Supabase Dashboard → SQL Editor
-- ═══════════════════════════════════════════════════════════════════════════

-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ── users ────────────────────────────────────────────────────────────────────
-- One row per staff user. The `id` must match the Supabase Auth user UUID
-- (auth.users.id) so that Flask-Login and Supabase Auth stay in sync.

CREATE TABLE IF NOT EXISTS public.users (
    id          UUID PRIMARY KEY,               -- matches auth.users.id
    name        TEXT        NOT NULL,
    email       TEXT        UNIQUE NOT NULL,
    role        TEXT        NOT NULL DEFAULT 'field_user'
                            CHECK (role IN ('admin', 'field_user')),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── customers ────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.customers (
    id                   UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    customer_id          TEXT UNIQUE NOT NULL,  -- e.g. CUS-20260415-0001
    full_name            TEXT NOT NULL,
    phone_number         TEXT,
    email                TEXT,
    date_of_birth        DATE,
    address              TEXT,
    aadhar_number        TEXT,
    pan_number           TEXT,
    kyc_document_url     TEXT,
    photo_url            TEXT,
    bank_name            TEXT,
    bank_account_number  TEXT,
    bank_ifsc_code       TEXT,
    bank_branch          TEXT,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by           UUID REFERENCES public.users(id) ON DELETE SET NULL
);

-- ── loans ─────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.loans (
    id                     UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    loan_id                TEXT UNIQUE NOT NULL,  -- e.g. LN-20260415-0001
    customer_id            UUID NOT NULL REFERENCES public.customers(id) ON DELETE CASCADE,

    -- Input parameters
    principal_amount       NUMERIC(15,2) NOT NULL,
    interest_rate_percent  NUMERIC(7,4)  NOT NULL,
    loan_duration_days     INTEGER       NOT NULL,
    penalty_rate_percent   NUMERIC(7,4)  NOT NULL DEFAULT 1.0,

    -- Derived / calculated fields
    total_interest_amount  NUMERIC(15,2) NOT NULL,
    total_repayable_amount NUMERIC(15,2) NOT NULL,
    daily_emi              NUMERIC(15,2) NOT NULL,

    -- Dates
    disbursement_date      DATE NOT NULL,
    due_date               DATE NOT NULL,  -- disbursement_date + loan_duration_days

    -- Live state
    status                 TEXT NOT NULL DEFAULT 'active'
                           CHECK (status IN ('active', 'overdue', 'cleared')),
    outstanding_balance    NUMERIC(15,2) NOT NULL,  -- starts = total_repayable_amount
    penalty_balance        NUMERIC(15,2) NOT NULL DEFAULT 0.00,

    -- Metadata
    created_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by             UUID REFERENCES public.users(id) ON DELETE SET NULL,
    assigned_to            UUID REFERENCES public.users(id) ON DELETE SET NULL
);

-- ── payments ──────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.payments (
    id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    loan_id          UUID NOT NULL REFERENCES public.loans(id) ON DELETE CASCADE,
    customer_id      UUID NOT NULL REFERENCES public.customers(id) ON DELETE CASCADE,
    amount_paid      NUMERIC(15,2) NOT NULL,
    payment_date     TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    collected_by     UUID REFERENCES public.users(id) ON DELETE SET NULL,
    balance_before   NUMERIC(15,2) NOT NULL,
    balance_after    NUMERIC(15,2) NOT NULL,
    penalty_included NUMERIC(15,2) NOT NULL DEFAULT 0.00,
    notes            TEXT
);

-- ── penalty_log ───────────────────────────────────────────────────────────────
-- One row per overdue loan per day. The scheduler writes here.

CREATE TABLE IF NOT EXISTS public.penalty_log (
    id                    UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    loan_id               UUID NOT NULL REFERENCES public.loans(id) ON DELETE CASCADE,
    penalty_date          DATE          NOT NULL,
    penalty_amount        NUMERIC(15,2) NOT NULL,
    balance_before_penalty NUMERIC(15,2) NOT NULL,
    balance_after_penalty  NUMERIC(15,2) NOT NULL,
    created_at            TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

-- Prevent duplicate penalty entries for the same loan on the same day
ALTER TABLE public.penalty_log
    ADD CONSTRAINT uq_penalty_loan_date UNIQUE (loan_id, penalty_date);

-- ── Indexes ───────────────────────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_loans_customer_id  ON public.loans(customer_id);
CREATE INDEX IF NOT EXISTS idx_loans_status        ON public.loans(status);
CREATE INDEX IF NOT EXISTS idx_loans_assigned_to   ON public.loans(assigned_to);
CREATE INDEX IF NOT EXISTS idx_loans_due_date      ON public.loans(due_date);

CREATE INDEX IF NOT EXISTS idx_payments_loan_id     ON public.payments(loan_id);
CREATE INDEX IF NOT EXISTS idx_payments_customer_id ON public.payments(customer_id);
CREATE INDEX IF NOT EXISTS idx_payments_collected_by ON public.payments(collected_by);
CREATE INDEX IF NOT EXISTS idx_payments_date        ON public.payments(payment_date);

CREATE INDEX IF NOT EXISTS idx_penalty_log_loan_id  ON public.penalty_log(loan_id);
CREATE INDEX IF NOT EXISTS idx_penalty_log_date     ON public.penalty_log(penalty_date);

CREATE INDEX IF NOT EXISTS idx_customers_created_by ON public.customers(created_by);

-- ════════════════════════════════════════════════════════════════════════════
-- HOW TO CREATE USERS
-- ════════════════════════════════════════════════════════════════════════════
--
-- 1. Go to Supabase Dashboard → Authentication → Users → "Add user"
--    Enter email + password. Note the UUID that Supabase assigns.
--
-- 2. Insert a matching row in public.users:
--
--   INSERT INTO public.users (id, name, email, role)
--   VALUES (
--     '<paste-supabase-auth-uuid-here>',
--     'Admin Name',
--     'admin@example.com',
--     'admin'
--   );
--
--   INSERT INTO public.users (id, name, email, role)
--   VALUES (
--     '<paste-supabase-auth-uuid-here>',
--     'Field User Name',
--     'fielduser@example.com',
--     'field_user'
--   );
-- ════════════════════════════════════════════════════════════════════════════
