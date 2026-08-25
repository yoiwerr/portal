package model

import (
	"time"

	"github.com/google/uuid"
)

// User represents a registered user.
type User struct {
	ID           uuid.UUID `json:"id"`
	Username     string    `json:"username"`
	PasswordHash string    `json:"-"`
	Role         string    `json:"role"`
	IsActive     bool      `json:"is_active"`
	CreatedAt    time.Time `json:"created_at"`
	UpdatedAt    time.Time `json:"updated_at"`
}

// ModelConfig represents an LLM model configuration.
// API keys are NEVER stored — only the env var name is stored.
type ModelConfig struct {
	ID             uuid.UUID `json:"id"`
	Alias          string    `json:"alias"`
	Provider       string    `json:"provider"`
	ModelName      string    `json:"model_name"`
	BaseURL        string    `json:"base_url"`
	APIKeyEnvVar   string    `json:"api_key_env_var"`
	IsDefault      bool      `json:"is_default"`
	IsEnabled      bool      `json:"is_enabled"`
	CreatedAt      time.Time `json:"created_at"`
	UpdatedAt      time.Time `json:"updated_at"`
}

// RequestLog records each HTTP request through the gateway.
type RequestLog struct {
	ID         uuid.UUID  `json:"id"`
	RequestID  string     `json:"request_id"`
	UserID     *uuid.UUID `json:"user_id,omitempty"`
	Method     string     `json:"method"`
	Path       string     `json:"path"`
	StatusCode int        `json:"status_code"`
	DurationMs int64      `json:"duration_ms"`
	ClientIP   string     `json:"client_ip"`
	CreatedAt  time.Time  `json:"created_at"`
}

// TokenUsage records token consumption for each LLM call.
type TokenUsage struct {
	ID           uuid.UUID  `json:"id"`
	RequestID    string     `json:"request_id"`
	UserID       *uuid.UUID `json:"user_id,omitempty"`
	Provider     string     `json:"provider"`
	ModelName    string     `json:"model_name"`
	InputTokens  int        `json:"input_tokens"`
	OutputTokens int        `json:"output_tokens"`
	TotalTokens  int        `json:"total_tokens"`
	DurationMs   int64      `json:"duration_ms"`
	Success      bool       `json:"success"`
	ErrorMessage string     `json:"error_message,omitempty"`
	CreatedAt    time.Time  `json:"created_at"`
}
