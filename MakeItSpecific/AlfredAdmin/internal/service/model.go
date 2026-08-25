package service

import (
	"context"
	"fmt"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/yoiwerr/portal/MakeItSpecific/AlfredAdmin/internal/model"
)

// ModelService handles model configuration CRUD.
type ModelService struct {
	db *pgxpool.Pool
}

// NewModelService creates a new ModelService.
func NewModelService(db *pgxpool.Pool) *ModelService {
	return &ModelService{db: db}
}

// CreateModelRequest is the request to create a model config.
type CreateModelRequest struct {
	Alias         string `json:"alias"`
	Provider      string `json:"provider"`
	ModelName     string `json:"model_name"`
	BaseURL       string `json:"base_url"`
	APIKeyEnvVar  string `json:"api_key_env_var"`
	IsEnabled     *bool  `json:"is_enabled,omitempty"`
}

// UpdateModelRequest is the request to update a model config.
type UpdateModelRequest struct {
	Alias        *string `json:"alias,omitempty"`
	Provider     *string `json:"provider,omitempty"`
	ModelName    *string `json:"model_name,omitempty"`
	BaseURL      *string `json:"base_url,omitempty"`
	APIKeyEnvVar *string `json:"api_key_env_var,omitempty"`
	IsEnabled    *bool   `json:"is_enabled,omitempty"`
}

// Create adds a new model configuration.
func (s *ModelService) Create(ctx context.Context, req CreateModelRequest) (*model.ModelConfig, error) {
	isEnabled := true
	if req.IsEnabled != nil {
		isEnabled = *req.IsEnabled
	}

	var m model.ModelConfig
	err := s.db.QueryRow(ctx,
		`INSERT INTO admin_model_configs (alias, provider, model_name, base_url, api_key_env_var, is_enabled)
		 VALUES ($1, $2, $3, $4, $5, $6)
		 RETURNING id, alias, provider, model_name, base_url, api_key_env_var, is_default, is_enabled, created_at, updated_at`,
		req.Alias, req.Provider, req.ModelName, req.BaseURL, req.APIKeyEnvVar, isEnabled,
	).Scan(&m.ID, &m.Alias, &m.Provider, &m.ModelName, &m.BaseURL, &m.APIKeyEnvVar, &m.IsDefault, &m.IsEnabled, &m.CreatedAt, &m.UpdatedAt)
	if err != nil {
		if isUniqueViolation(err) {
			return nil, fmt.Errorf("alias already exists")
		}
		return nil, fmt.Errorf("create model config: %w", err)
	}

	return &m, nil
}

// List returns all model configurations.
func (s *ModelService) List(ctx context.Context) ([]model.ModelConfig, error) {
	rows, err := s.db.Query(ctx,
		`SELECT id, alias, provider, model_name, base_url, api_key_env_var, is_default, is_enabled, created_at, updated_at
		 FROM admin_model_configs ORDER BY created_at DESC`,
	)
	if err != nil {
		return nil, fmt.Errorf("list model configs: %w", err)
	}
	defer rows.Close()

	var configs []model.ModelConfig
	for rows.Next() {
		var m model.ModelConfig
		if err := rows.Scan(&m.ID, &m.Alias, &m.Provider, &m.ModelName, &m.BaseURL, &m.APIKeyEnvVar, &m.IsDefault, &m.IsEnabled, &m.CreatedAt, &m.UpdatedAt); err != nil {
			return nil, fmt.Errorf("scan model config: %w", err)
		}
		configs = append(configs, m)
	}
	return configs, nil
}

// GetByID returns a single model config by ID.
func (s *ModelService) GetByID(ctx context.Context, id uuid.UUID) (*model.ModelConfig, error) {
	var m model.ModelConfig
	err := s.db.QueryRow(ctx,
		`SELECT id, alias, provider, model_name, base_url, api_key_env_var, is_default, is_enabled, created_at, updated_at
		 FROM admin_model_configs WHERE id = $1`, id,
	).Scan(&m.ID, &m.Alias, &m.Provider, &m.ModelName, &m.BaseURL, &m.APIKeyEnvVar, &m.IsDefault, &m.IsEnabled, &m.CreatedAt, &m.UpdatedAt)
	if err != nil {
		return nil, fmt.Errorf("model config not found: %w", err)
	}
	return &m, nil
}

// GetByAlias returns a model config by alias.
func (s *ModelService) GetByAlias(ctx context.Context, alias string) (*model.ModelConfig, error) {
	var m model.ModelConfig
	err := s.db.QueryRow(ctx,
		`SELECT id, alias, provider, model_name, base_url, api_key_env_var, is_default, is_enabled, created_at, updated_at
		 FROM admin_model_configs WHERE alias = $1`, alias,
	).Scan(&m.ID, &m.Alias, &m.Provider, &m.ModelName, &m.BaseURL, &m.APIKeyEnvVar, &m.IsDefault, &m.IsEnabled, &m.CreatedAt, &m.UpdatedAt)
	if err != nil {
		return nil, fmt.Errorf("model config not found: %w", err)
	}
	return &m, nil
}

// GetDefault returns the default enabled model config.
func (s *ModelService) GetDefault(ctx context.Context) (*model.ModelConfig, error) {
	var m model.ModelConfig
	err := s.db.QueryRow(ctx,
		`SELECT id, alias, provider, model_name, base_url, api_key_env_var, is_default, is_enabled, created_at, updated_at
		 FROM admin_model_configs WHERE is_default = true AND is_enabled = true LIMIT 1`,
	).Scan(&m.ID, &m.Alias, &m.Provider, &m.ModelName, &m.BaseURL, &m.APIKeyEnvVar, &m.IsDefault, &m.IsEnabled, &m.CreatedAt, &m.UpdatedAt)
	if err != nil {
		return nil, fmt.Errorf("no default model config: %w", err)
	}
	return &m, nil
}

// Update modifies an existing model configuration.
func (s *ModelService) Update(ctx context.Context, id uuid.UUID, req UpdateModelRequest) (*model.ModelConfig, error) {
	// Fetch existing
	existing, err := s.GetByID(ctx, id)
	if err != nil {
		return nil, err
	}

	// Apply partial updates
	if req.Alias != nil {
		existing.Alias = *req.Alias
	}
	if req.Provider != nil {
		existing.Provider = *req.Provider
	}
	if req.ModelName != nil {
		existing.ModelName = *req.ModelName
	}
	if req.BaseURL != nil {
		existing.BaseURL = *req.BaseURL
	}
	if req.APIKeyEnvVar != nil {
		existing.APIKeyEnvVar = *req.APIKeyEnvVar
	}
	if req.IsEnabled != nil {
		existing.IsEnabled = *req.IsEnabled
	}
	existing.UpdatedAt = time.Now()

	_, err = s.db.Exec(ctx,
		`UPDATE admin_model_configs SET alias=$1, provider=$2, model_name=$3, base_url=$4, api_key_env_var=$5, is_enabled=$6, updated_at=$7
		 WHERE id=$8`,
		existing.Alias, existing.Provider, existing.ModelName, existing.BaseURL, existing.APIKeyEnvVar, existing.IsEnabled, existing.UpdatedAt, id,
	)
	if err != nil {
		if isUniqueViolation(err) {
			return nil, fmt.Errorf("alias already exists")
		}
		return nil, fmt.Errorf("update model config: %w", err)
	}

	return existing, nil
}

// Delete removes a model configuration. Cannot delete the default model.
func (s *ModelService) Delete(ctx context.Context, id uuid.UUID) error {
	var isDefault bool
	err := s.db.QueryRow(ctx, `SELECT is_default FROM admin_model_configs WHERE id=$1`, id).Scan(&isDefault)
	if err != nil {
		return fmt.Errorf("model config not found: %w", err)
	}
	if isDefault {
		return fmt.Errorf("cannot delete the default model — set another model as default first")
	}

	_, err = s.db.Exec(ctx, `DELETE FROM admin_model_configs WHERE id=$1`, id)
	return err
}

// Toggle enables or disables a model config.
func (s *ModelService) Toggle(ctx context.Context, id uuid.UUID, enabled bool) error {
	_, err := s.db.Exec(ctx, `UPDATE admin_model_configs SET is_enabled=$1, updated_at=$2 WHERE id=$3`, enabled, time.Now(), id)
	return err
}

// SetDefault sets a model as the default. Unsets the previous default first.
func (s *ModelService) SetDefault(ctx context.Context, id uuid.UUID) error {
	tx, err := s.db.Begin(ctx)
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx)

	if _, err := tx.Exec(ctx, `UPDATE admin_model_configs SET is_default=false, updated_at=$1 WHERE is_default=true`, time.Now()); err != nil {
		return err
	}
	if _, err := tx.Exec(ctx, `UPDATE admin_model_configs SET is_default=true, updated_at=$1 WHERE id=$2`, time.Now(), id); err != nil {
		return err
	}

	return tx.Commit(ctx)
}

// SeedDefault creates the default DeepSeek model config if none exist.
func (s *ModelService) SeedDefault(ctx context.Context) error {
	var count int
	err := s.db.QueryRow(ctx, `SELECT COUNT(*) FROM admin_model_configs`).Scan(&count)
	if err != nil {
		return err
	}
	if count > 0 {
		return nil
	}

	_, err = s.db.Exec(ctx,
		`INSERT INTO admin_model_configs (alias, provider, model_name, base_url, api_key_env_var, is_default, is_enabled)
		 VALUES ('deepseek-chat', 'deepseek', 'deepseek-chat', 'https://api.deepseek.com/v1', 'DEEPSEEK_API_KEY', true, true)`,
	)
	return err
}
