-- Existing Go auth migration must run first. Do not touch its tables or history.
CREATE TABLE public.dude_projects (
    id uuid PRIMARY KEY,
    owner_id uuid NOT NULL REFERENCES public.admin_users(id) ON DELETE CASCADE,
    title text NOT NULL CHECK (length(trim(title)) BETWEEN 1 AND 120),
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX dude_projects_owner ON public.dude_projects(owner_id, created_at DESC, id);

CREATE TABLE public.dude_brief_drafts (
    project_id uuid PRIMARY KEY REFERENCES public.dude_projects(id) ON DELETE CASCADE,
    revision integer NOT NULL CHECK (revision > 0),
    content jsonb NOT NULL CHECK (jsonb_typeof(content) = 'object' AND content @> '{"schema_version":1}'),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE public.dude_brief_versions (
    id uuid PRIMARY KEY,
    project_id uuid NOT NULL REFERENCES public.dude_projects(id) ON DELETE CASCADE,
    version integer NOT NULL CHECK (version > 0),
    draft_revision integer NOT NULL CHECK (draft_revision > 0),
    schema_version integer NOT NULL CHECK (schema_version = 1),
    content jsonb NOT NULL CHECK (jsonb_typeof(content) = 'object' AND content @> '{"schema_version":1}'),
    wiki jsonb NOT NULL CHECK (jsonb_typeof(wiki) = 'object'),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(project_id, version),
    UNIQUE(id, project_id)
);

CREATE TABLE public.dude_generation_runs (
    id uuid PRIMARY KEY,
    project_id uuid NOT NULL REFERENCES public.dude_projects(id) ON DELETE CASCADE,
    brief_version_id uuid NOT NULL,
    idempotency_key text NOT NULL CHECK (length(idempotency_key) BETWEEN 1 AND 128),
    status text NOT NULL CHECK (status IN ('running', 'succeeded', 'failed')),
    error_code text CHECK (error_code IN ('model_error', 'invalid_output', 'cancelled', 'interrupted')),
    created_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    FOREIGN KEY (brief_version_id, project_id) REFERENCES public.dude_brief_versions(id, project_id) ON DELETE CASCADE,
    UNIQUE(project_id, idempotency_key),
    UNIQUE(id, brief_version_id, project_id),
    CHECK ((status = 'running' AND finished_at IS NULL AND error_code IS NULL)
        OR (status = 'succeeded' AND finished_at IS NOT NULL AND error_code IS NULL)
        OR (status = 'failed' AND finished_at IS NOT NULL AND error_code IS NOT NULL))
);
CREATE UNIQUE INDEX dude_one_running_generation ON public.dude_generation_runs(project_id) WHERE status = 'running';

-- A delivery is one row containing both documents, never two independently published records.
CREATE TABLE public.dude_artifact_versions (
    id uuid PRIMARY KEY,
    project_id uuid NOT NULL REFERENCES public.dude_projects(id) ON DELETE CASCADE,
    brief_version_id uuid NOT NULL,
    run_id uuid NOT NULL UNIQUE,
    technical_plan text NOT NULL CHECK (length(trim(technical_plan)) BETWEEN 1 AND 200000),
    demo_guide text NOT NULL CHECK (length(trim(demo_guide)) BETWEEN 1 AND 200000),
    created_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (run_id, brief_version_id, project_id)
        REFERENCES public.dude_generation_runs(id, brief_version_id, project_id) ON DELETE CASCADE,
    UNIQUE(project_id, brief_version_id)
);

CREATE FUNCTION public.dude_reject_version_update() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'dude version records are immutable';
END;
$$;
CREATE TRIGGER dude_brief_immutable BEFORE UPDATE ON public.dude_brief_versions
    FOR EACH ROW EXECUTE FUNCTION public.dude_reject_version_update();
CREATE TRIGGER dude_artifact_immutable BEFORE UPDATE ON public.dude_artifact_versions
    FOR EACH ROW EXECUTE FUNCTION public.dude_reject_version_update();

-- Deferred checks allow status + pair insertion in either order, but require both at COMMIT.
CREATE FUNCTION public.dude_check_delivery() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE run_uuid uuid;
BEGIN
    IF TG_TABLE_NAME = 'dude_generation_runs' THEN run_uuid := NEW.id;
    ELSIF TG_OP = 'DELETE' THEN run_uuid := OLD.run_id;
    ELSE run_uuid := NEW.run_id;
    END IF;
    IF EXISTS (
        SELECT 1 FROM public.dude_generation_runs r
        WHERE r.id = run_uuid AND
        ((r.status = 'succeeded') <> EXISTS(SELECT 1 FROM public.dude_artifact_versions a WHERE a.run_id = r.id))
    ) THEN RAISE EXCEPTION 'successful generation must have exactly one complete delivery';
    END IF;
    RETURN NULL;
END;
$$;
CREATE CONSTRAINT TRIGGER dude_run_delivery AFTER INSERT OR UPDATE ON public.dude_generation_runs
    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.dude_check_delivery();
CREATE CONSTRAINT TRIGGER dude_artifact_delivery AFTER INSERT OR DELETE ON public.dude_artifact_versions
    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.dude_check_delivery();
