package config

import (
	"os"
	"time"
)

// Config holds all configuration for the Admin service.
type Config struct {
	// Server
	Port string `json:"port"`

	// JWT (shared secret with Alfred/Python)
	JWTSecret        string        `json:"jwt_secret"`
	JWTAccessExpiry  time.Duration `json:"jwt_access_expiry"`
	JWTRefreshExpiry time.Duration `json:"jwt_refresh_expiry"`

	// Admin seed
	AdminInitPassword string `json:"admin_init_password"`

	// Database (shared alfred DB)
	DatabaseURL string `json:"database_url"`

	// LLM Provider keys (read from env at runtime, never logged)
	DeepSeekAPIKey  string `json:"-"`
	OpenAIAPIKey    string `json:"-"`
	DashScopeAPIKey string `json:"-"`
}

// Load reads configuration from environment variables.
func Load() *Config {
	cfg := &Config{
		Port:              getEnv("ADMIN_PORT", "8080"),
		JWTSecret:         getEnv("JWT_SECRET", "change-me-in-production-min-32-chars!!"),
		JWTAccessExpiry:   getEnvDuration("JWT_ACCESS_EXPIRY", 15*time.Minute),
		JWTRefreshExpiry:  getEnvDuration("JWT_REFRESH_EXPIRY", 7*24*time.Hour),
		AdminInitPassword: getEnv("ADMIN_INIT_PASSWORD", "admin123"),
		DatabaseURL:       getEnv("DATABASE_URL", "postgres://postgres:postgres@localhost:5432/alfred?sslmode=disable"),
		DeepSeekAPIKey:    os.Getenv("DEEPSEEK_API_KEY"),
		OpenAIAPIKey:      os.Getenv("OPENAI_API_KEY"),
		DashScopeAPIKey:   os.Getenv("DASHSCOPE_API_KEY"),
	}
	return cfg
}

func getEnv(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

func getEnvInt(key string, fallback int) int {
	s := os.Getenv(key)
	if s == "" {
		return fallback
	}
	var n int
	for _, c := range s {
		if c < '0' || c > '9' {
			return fallback
		}
		n = n*10 + int(c-'0')
	}
	return n
}

func getEnvDuration(key string, fallback time.Duration) time.Duration {
	s := os.Getenv(key)
	if s == "" {
		return fallback
	}
	d, err := time.ParseDuration(s)
	if err != nil {
		return fallback
	}
	return d
}

// GetAPIKey returns the actual API key for a given env var name.
func (c *Config) GetAPIKey(envVarName string) string {
	switch envVarName {
	case "DEEPSEEK_API_KEY":
		return c.DeepSeekAPIKey
	case "OPENAI_API_KEY":
		return c.OpenAIAPIKey
	case "DASHSCOPE_API_KEY":
		return c.DashScopeAPIKey
	default:
		return os.Getenv(envVarName)
	}
}
