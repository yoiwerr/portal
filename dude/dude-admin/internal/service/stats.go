package service

import (
	"context"
	"fmt"

	"github.com/jackc/pgx/v5/pgxpool"
)

// StatsService provides token usage and request statistics from admin_* tables.
type StatsService struct {
	db *pgxpool.Pool
}

// NewStatsService creates a new StatsService.
func NewStatsService(db *pgxpool.Pool) *StatsService {
	return &StatsService{db: db}
}

// TokenStats represents aggregate token usage statistics.
type TokenStats struct {
	TotalCalls    int64   `json:"total_calls"`
	TotalTokens   int64   `json:"total_tokens"`
	InputTokens   int64   `json:"input_tokens"`
	OutputTokens  int64   `json:"output_tokens"`
	AvgDurationMs float64 `json:"avg_duration_ms"`
	SuccessCount  int64   `json:"success_count"`
	FailureCount  int64   `json:"failure_count"`
	SuccessRate   float64 `json:"success_rate"`
}

// ModelBreakdown represents per-model statistics.
type ModelBreakdown struct {
	ModelName     string  `json:"model_name"`
	TotalCalls    int64   `json:"total_calls"`
	TotalTokens   int64   `json:"total_tokens"`
	InputTokens   int64   `json:"input_tokens"`
	OutputTokens  int64   `json:"output_tokens"`
	AvgDurationMs float64 `json:"avg_duration_ms"`
}

// TokenUsageRow is a single token usage record.
type TokenUsageRow struct {
	ID           string  `json:"id"`
	UserID       *string `json:"user_id"`
	SessionID    string  `json:"session_id"`
	Provider     string  `json:"provider"`
	ModelName    string  `json:"model_name"`
	InputTokens  int     `json:"input_tokens"`
	OutputTokens int     `json:"output_tokens"`
	TotalTokens  int     `json:"total_tokens"`
	DurationMs   float64 `json:"duration_ms"`
	Success      bool    `json:"success"`
	ErrorMessage string  `json:"error_message"`
	CreatedAt    string  `json:"created_at"`
}

// TokenStatsResponse is the full stats response.
type TokenStatsResponse struct {
	Summary TokenStats        `json:"summary"`
	ByModel []ModelBreakdown  `json:"by_model"`
	Recent  []TokenUsageRow   `json:"recent"`
}

// GetTokenStats returns aggregated token usage statistics.
func (s *StatsService) GetTokenStats(ctx context.Context) (*TokenStatsResponse, error) {
	resp := &TokenStatsResponse{}

	err := s.db.QueryRow(ctx,
		`SELECT
			COUNT(*) as total_calls,
			COALESCE(SUM(total_tokens), 0) as total_tokens,
			COALESCE(SUM(input_tokens), 0) as input_tokens,
			COALESCE(SUM(output_tokens), 0) as output_tokens,
			COALESCE(AVG(duration_ms), 0) as avg_duration_ms,
			COUNT(*) FILTER (WHERE success = true) as success_count,
			COUNT(*) FILTER (WHERE success = false) as failure_count
		 FROM admin_token_usage`,
	).Scan(
		&resp.Summary.TotalCalls,
		&resp.Summary.TotalTokens,
		&resp.Summary.InputTokens,
		&resp.Summary.OutputTokens,
		&resp.Summary.AvgDurationMs,
		&resp.Summary.SuccessCount,
		&resp.Summary.FailureCount,
	)
	if err != nil {
		return nil, fmt.Errorf("query token stats: %w", err)
	}

	if resp.Summary.TotalCalls > 0 {
		resp.Summary.SuccessRate = float64(resp.Summary.SuccessCount) / float64(resp.Summary.TotalCalls) * 100
	}

	// Per-model breakdown
	rows, err := s.db.Query(ctx,
		`SELECT
			model_name,
			COUNT(*) as total_calls,
			COALESCE(SUM(total_tokens), 0) as total_tokens,
			COALESCE(SUM(input_tokens), 0) as input_tokens,
			COALESCE(SUM(output_tokens), 0) as output_tokens,
			COALESCE(AVG(duration_ms), 0) as avg_duration_ms
		 FROM admin_token_usage
		 GROUP BY model_name
		 ORDER BY total_calls DESC`,
	)
	if err != nil {
		return nil, fmt.Errorf("query model breakdown: %w", err)
	}
	defer rows.Close()

	for rows.Next() {
		var mb ModelBreakdown
		if err := rows.Scan(&mb.ModelName, &mb.TotalCalls, &mb.TotalTokens, &mb.InputTokens, &mb.OutputTokens, &mb.AvgDurationMs); err != nil {
			return nil, fmt.Errorf("scan model breakdown: %w", err)
		}
		resp.ByModel = append(resp.ByModel, mb)
	}

	// Recent calls
	recentRows, err := s.db.Query(ctx,
		`SELECT id, user_id, session_id, provider, model_name, input_tokens, output_tokens, total_tokens, duration_ms, success, error_message, created_at
		 FROM admin_token_usage
		 ORDER BY created_at DESC
		 LIMIT 50`,
	)
	if err != nil {
		return nil, fmt.Errorf("query recent usage: %w", err)
	}
	defer recentRows.Close()

	for recentRows.Next() {
		var tu TokenUsageRow
		if err := recentRows.Scan(&tu.ID, &tu.UserID, &tu.SessionID, &tu.Provider, &tu.ModelName, &tu.InputTokens, &tu.OutputTokens, &tu.TotalTokens, &tu.DurationMs, &tu.Success, &tu.ErrorMessage, &tu.CreatedAt); err != nil {
			return nil, fmt.Errorf("scan recent usage: %w", err)
		}
		resp.Recent = append(resp.Recent, tu)
	}

	return resp, nil
}

// GetRecentUsage returns only the most recent 50 token usage records.
func (s *StatsService) GetRecentUsage(ctx context.Context) ([]TokenUsageRow, error) {
	rows, err := s.db.Query(ctx,
		`SELECT id, user_id, session_id, provider, model_name, input_tokens, output_tokens, total_tokens, duration_ms, success, error_message, created_at
		 FROM admin_token_usage
		 ORDER BY created_at DESC
		 LIMIT 50`,
	)
	if err != nil {
		return nil, fmt.Errorf("query recent usage: %w", err)
	}
	defer rows.Close()

	var recent []TokenUsageRow
	for rows.Next() {
		var tu TokenUsageRow
		if err := rows.Scan(&tu.ID, &tu.UserID, &tu.SessionID, &tu.Provider, &tu.ModelName, &tu.InputTokens, &tu.OutputTokens, &tu.TotalTokens, &tu.DurationMs, &tu.Success, &tu.ErrorMessage, &tu.CreatedAt); err != nil {
			return nil, fmt.Errorf("scan recent usage: %w", err)
		}
		recent = append(recent, tu)
	}
	if recent == nil {
		recent = []TokenUsageRow{}
	}
	return recent, nil
}

// RequestStats represents request log statistics.
type RequestStats struct {
	TotalRequests int64   `json:"total_requests"`
	AvgDurationMs float64 `json:"avg_duration_ms"`
	Status2xx     int64   `json:"status_2xx"`
	Status4xx     int64   `json:"status_4xx"`
	Status5xx     int64   `json:"status_5xx"`
}

// GetRequestStats returns request log statistics.
func (s *StatsService) GetRequestStats(ctx context.Context) (*RequestStats, error) {
	var rs RequestStats
	err := s.db.QueryRow(ctx,
		`SELECT
			COUNT(*) as total_requests,
			COALESCE(AVG(duration_ms), 0) as avg_duration_ms,
			COUNT(*) FILTER (WHERE status_code >= 200 AND status_code < 300) as status_2xx,
			COUNT(*) FILTER (WHERE status_code >= 400 AND status_code < 500) as status_4xx,
			COUNT(*) FILTER (WHERE status_code >= 500) as status_5xx
		 FROM admin_request_logs`,
	).Scan(&rs.TotalRequests, &rs.AvgDurationMs, &rs.Status2xx, &rs.Status4xx, &rs.Status5xx)
	if err != nil {
		return nil, fmt.Errorf("query request stats: %w", err)
	}
	return &rs, nil
}
