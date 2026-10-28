package service

import (
	"context"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
)

// UserDirectory exposes account metadata and recorded usage, never credentials.
type UserDirectory struct{ db *pgxpool.Pool }

func NewUserDirectory(db *pgxpool.Pool) *UserDirectory { return &UserDirectory{db: db} }

type UserUsage struct {
	ID           string     `json:"id"`
	Username     string     `json:"username"`
	Role         string     `json:"role"`
	IsActive     bool       `json:"is_active"`
	CreatedAt    time.Time  `json:"created_at"`
	Calls        int64      `json:"calls"`
	InputTokens  int64      `json:"input_tokens"`
	OutputTokens int64      `json:"output_tokens"`
	TotalTokens  int64      `json:"total_tokens"`
	LastUsedAt   *time.Time `json:"last_used_at"`
}

type UserPage struct {
	Users       []UserUsage `json:"users"`
	Total       int64       `json:"total"`
	Page        int         `json:"page"`
	PageSize    int         `json:"page_size"`
	PeriodStart time.Time   `json:"period_start"`
	AsOf        time.Time   `json:"as_of"`
}

type UsageOverview struct {
	TotalUsers   int64     `json:"total_users"`
	AdminUsers   int64     `json:"admin_users"`
	ActiveUsers  int64     `json:"active_users"`
	Calls        int64     `json:"calls"`
	InputTokens  int64     `json:"input_tokens"`
	OutputTokens int64     `json:"output_tokens"`
	TotalTokens  int64     `json:"total_tokens"`
	PeriodStart  time.Time `json:"period_start"`
	AsOf         time.Time `json:"as_of"`
}

func (s *UserDirectory) Overview(ctx context.Context) (*UsageOverview, error) {
	now := time.Now().UTC()
	result := &UsageOverview{AsOf: now, PeriodStart: now.Add(-30 * 24 * time.Hour)}
	err := s.db.QueryRow(ctx, `SELECT COUNT(*), COUNT(*) FILTER (WHERE role='admin'),
		COUNT(*) FILTER (WHERE is_active) FROM admin_users`).Scan(
		&result.TotalUsers, &result.AdminUsers, &result.ActiveUsers)
	if err != nil {
		return nil, fmt.Errorf("count accounts: %w", err)
	}
	err = s.db.QueryRow(ctx, `SELECT COUNT(*), COALESCE(SUM(input_tokens),0),
		COALESCE(SUM(output_tokens),0), COALESCE(SUM(total_tokens),0)
		FROM admin_token_usage WHERE created_at >= $1 AND created_at <= $2`, result.PeriodStart, now).Scan(
		&result.Calls, &result.InputTokens, &result.OutputTokens, &result.TotalTokens)
	if err != nil {
		return nil, fmt.Errorf("summarize usage: %w", err)
	}
	return result, nil
}

func (s *UserDirectory) List(ctx context.Context, search, role string, page, pageSize int) (*UserPage, error) {
	if page < 1 || page > 1000000 || pageSize < 1 || pageSize > 100 || (role != "" && role != "admin" && role != "user") {
		return nil, fmt.Errorf("invalid directory filters")
	}
	now := time.Now().UTC()
	result := &UserPage{Users: []UserUsage{}, Page: page, PageSize: pageSize,
		AsOf: now, PeriodStart: now.Add(-30 * 24 * time.Hour)}
	// strpos treats '%' and '_' literally; all user input remains parameterized.
	filter := ` WHERE ($1='' OR strpos(lower(username),lower($1))>0 OR id::text=$1)
		AND ($2='' OR role=$2)`
	if err := s.db.QueryRow(ctx, `SELECT COUNT(*) FROM admin_users`+filter, search, role).Scan(&result.Total); err != nil {
		return nil, fmt.Errorf("count filtered accounts: %w", err)
	}
	rows, err := s.db.Query(ctx, `WITH accounts AS (
		SELECT id,username,role,is_active,created_at FROM admin_users`+filter+`
		ORDER BY created_at DESC,id LIMIT $3 OFFSET $4
	) SELECT a.id::text,a.username,a.role,a.is_active,a.created_at,
		u.calls,u.input_tokens,u.output_tokens,u.total_tokens,u.last_used_at
	FROM accounts a LEFT JOIN LATERAL (
		SELECT COUNT(*) AS calls, COALESCE(SUM(input_tokens),0) AS input_tokens,
		COALESCE(SUM(output_tokens),0) AS output_tokens, COALESCE(SUM(total_tokens),0) AS total_tokens,
		MAX(created_at) AS last_used_at
		FROM admin_token_usage WHERE user_id=a.id AND created_at >= $5 AND created_at <= $6
	) u ON true ORDER BY a.created_at DESC,a.id`, search, role, pageSize, (page-1)*pageSize, result.PeriodStart, now)
	if err != nil {
		return nil, fmt.Errorf("list accounts and usage: %w", err)
	}
	defer rows.Close()
	for rows.Next() {
		var user UserUsage
		if err := rows.Scan(&user.ID, &user.Username, &user.Role, &user.IsActive, &user.CreatedAt,
			&user.Calls, &user.InputTokens, &user.OutputTokens, &user.TotalTokens, &user.LastUsedAt); err != nil {
			return nil, fmt.Errorf("read account usage: %w", err)
		}
		result.Users = append(result.Users, user)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("read accounts: %w", err)
	}
	return result, nil
}
