package store

import (
	"context"
	"fmt"
	"log/slog"
	"os"
	"path/filepath"
	"sort"
	"strings"

	"github.com/jackc/pgx/v5/pgxpool"
)

// Postgres holds the connection pool.
type Postgres struct {
	Pool *pgxpool.Pool
}

// NewPostgres creates a new PostgreSQL connection pool and runs migrations.
func NewPostgres(ctx context.Context, databaseURL string) (*Postgres, error) {
	cfg, err := pgxpool.ParseConfig(databaseURL)
	if err != nil {
		return nil, fmt.Errorf("parse database URL: %w", err)
	}
	cfg.MaxConns = 20
	cfg.MinConns = 2

	pool, err := pgxpool.NewWithConfig(ctx, cfg)
	if err != nil {
		return nil, fmt.Errorf("create connection pool: %w", err)
	}

	if err := pool.Ping(ctx); err != nil {
		pool.Close()
		return nil, fmt.Errorf("ping database: %w", err)
	}

	slog.Info("connected to PostgreSQL",
		"host", cfg.ConnConfig.Host,
		"port", cfg.ConnConfig.Port,
		"database", cfg.ConnConfig.Database,
	)

	return &Postgres{Pool: pool}, nil
}

// RunMigrations reads and executes SQL migration files in order.
// Uses admin_schema_migrations table to skip already-applied migrations.
func (p *Postgres) RunMigrations(ctx context.Context, migrationsDir string) error {
	// Ensure the migration tracking table exists before we check it.
	_, _ = p.Pool.Exec(ctx, `CREATE TABLE IF NOT EXISTS admin_schema_migrations (
		version VARCHAR(64) PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
	)`)

	// Load already-applied migration versions.
	applied := make(map[string]bool)
	rows, err := p.Pool.Query(ctx, `SELECT version FROM admin_schema_migrations`)
	if err == nil {
		defer rows.Close()
		for rows.Next() {
			var v string
			if err := rows.Scan(&v); err == nil {
				applied[v] = true
			}
		}
	}

	entries, err := os.ReadDir(migrationsDir)
	if err != nil {
		return fmt.Errorf("read migrations dir %s: %w", migrationsDir, err)
	}

	var upFiles []string
	for _, e := range entries {
		if !e.IsDir() && strings.HasSuffix(e.Name(), ".up.sql") {
			upFiles = append(upFiles, e.Name())
		}
	}
	sort.Strings(upFiles)

	for _, f := range upFiles {
		version := strings.TrimSuffix(f, ".up.sql")
		if applied[version] {
			slog.Info("migration skipped (already applied)", "file", f)
			continue
		}

		path := filepath.Join(migrationsDir, f)
		sql, err := os.ReadFile(path)
		if err != nil {
			return fmt.Errorf("read migration %s: %w", f, err)
		}

		tx, err := p.Pool.Begin(ctx)
		if err != nil {
			return fmt.Errorf("begin tx for migration %s: %w", f, err)
		}
		defer tx.Rollback(ctx)

		if _, err := tx.Exec(ctx, string(sql)); err != nil {
			return fmt.Errorf("execute migration %s: %w", f, err)
		}

		if _, err := tx.Exec(ctx,
			`INSERT INTO admin_schema_migrations (version) VALUES ($1)`, version); err != nil {
			return fmt.Errorf("record migration %s: %w", f, err)
		}

		if err := tx.Commit(ctx); err != nil {
			return fmt.Errorf("commit migration %s: %w", f, err)
		}
		slog.Info("migration applied", "file", f)
	}

	return nil
}

// Close closes the connection pool.
func (p *Postgres) Close() {
	p.Pool.Close()
}
